// The parts of the player that have no interface code in them: the spectrum display's numbers and
// the play queue.

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <numbers>
#include <vector>

#include "check.h"
#include "play_queue.h"
#include "spectrum.h"

namespace
{

using namespace korre;

std::vector<float> sine(double hz, double amplitude, double sample_rate, std::size_t n)
{
    std::vector<float> x(n);
    for (std::size_t i = 0; i < n; ++i)
    {
        x[i] = static_cast<float>(amplitude * std::sin(2 * std::numbers::pi * hz * static_cast<double>(i) / sample_rate));
    }
    return x;
}

void test_spectrum()
{
    // The columns run from 20 Hz to 20 kHz in even steps of pitch.
    CHECK(spectrum::column_of(20.0) == 0);
    CHECK(spectrum::column_of(19999.0) == 99);
    CHECK(spectrum::column_of(5.0) == 0 && spectrum::column_of(30000.0) == 99);
    CHECK(spectrum::column_of(632.5) == 50); // the geometric middle of 20 Hz and 20 kHz
    CHECK(spectrum::column_of(200.0) == 33 && spectrum::column_of(2000.0) == 66);

    for (const double rate : {44100.0, 48000.0, 96000.0})
    {
        for (const double hz : {100.0, 1000.0, 10000.0})
        {
            spectrum s;
            s.set_sample_rate(rate);
            s.feed(sine(hz, 0.5, rate, static_cast<std::size_t>(rate))); // one second
            s.update(0.02);

            // The strongest column is the tone's, and it reads the tone's level: -6 dB for amplitude 0.5.
            int strongest = 0;
            for (int c = 1; c < spectrum::columns; ++c)
            {
                if (s.column_db(c) > s.column_db(strongest))
                {
                    strongest = c;
                }
            }
            const std::string what = std::to_string(static_cast<int>(hz)) + " Hz at " + std::to_string(static_cast<int>(rate));
            CHECK_MSG(std::abs(strongest - spectrum::column_of(hz)) <= 1, what + ": strongest column " + std::to_string(strongest));
            double total = 0;
            for (int c = 0; c < spectrum::columns; ++c)
            {
                total += std::pow(10.0, s.column_db(c) / 10.0);
            }
            CHECK_MSG(std::fabs(10 * std::log10(total) - (-6.02)) < 0.5, what + ": level over all columns " + std::to_string(10 * std::log10(total)) + " dB");
            // Far from the tone there is nothing: the window keeps it from smearing.
            const int far = spectrum::column_of(hz) > 50 ? 10 : 90;
            CHECK_MSG(s.column_db(far) < -90.0, what + ": far column " + std::to_string(s.column_db(far)) + " dB");
            // What is plotted is that level on the display's scale.
            const float plotted = s.values()[strongest];
            const double expected = (s.column_db(strongest) - spectrum::floor_db) / (spectrum::top_db - spectrum::floor_db);
            CHECK_NEAR(plotted, std::clamp(expected, 0.0, 1.0), 1e-5);
        }
    }

    // Columns rise at once and fall at a fixed rate; with no sound they reach zero.
    spectrum s;
    s.set_sample_rate(48000);
    s.feed(sine(1000, 0.5, 48000, 48000));
    s.update(0.02);
    const int c = spectrum::column_of(1000);
    const float lit = s.values()[c];
    CHECK(lit > 0.9f);
    s.decay(0.5);
    CHECK(s.values()[c] < lit && s.values()[c] > 0.5f);
    s.decay(10.0);
    CHECK(s.values()[c] == 0.0f);
    s.update(0.02); // decay() also forgets the samples
    CHECK(s.values()[c] == 0.0f);
}

void test_queue()
{
    play_queue q;
    CHECK(q.current() == nullptr && !q.next() && !q.previous() && !q.finished());

    for (const char* name : {"a.flac", "b.flac", "c.flac", "d.flac", "e.flac"})
    {
        CHECK(q.add(name) == 1);
    }
    CHECK(*q.current() == "a.flac" && q.upcoming().size() == 5);

    CHECK(q.next());
    CHECK(*q.current() == "b.flac" && q.history().front().path == "a.flac");
    CHECK(q.previous());
    CHECK(*q.current() == "a.flac" && q.history().empty());

    // Repeat keeps the current track when it ends; without it the queue moves on.
    q.repeat_one = true;
    CHECK(q.finished() && *q.current() == "a.flac");
    q.repeat_one = false;
    CHECK(q.finished() && *q.current() == "b.flac");

    // Shuffle leaves the current track alone and keeps every track; switching it off restores the order.
    q.set_shuffle(true);
    CHECK(q.shuffle() && *q.current() == "b.flac" && q.upcoming().size() == 4);
    q.set_shuffle(false);
    CHECK(q.upcoming()[1].path == "c.flac" && q.upcoming()[2].path == "d.flac" && q.upcoming()[3].path == "e.flac");

    // DEL takes away the track added last, wherever it sits.
    q.set_shuffle(true);
    q.remove_last();
    bool gone = true;
    for (const auto& e : q.upcoming())
    {
        gone = gone && e.path != "e.flac";
    }
    CHECK(gone && q.upcoming().size() == 3);
    q.set_shuffle(false);

    // The last track: next() leaves nothing current.
    CHECK(q.next() && q.next());
    CHECK(!q.next());
    CHECK(q.current() == nullptr && q.history().size() == 4);
    q.clear();
    CHECK(q.upcoming().empty() && q.history().size() == 4);

    // A playlist: one path per line, relative ones from the playlist's folder, blank lines skipped.
    const auto dir = std::filesystem::temp_directory_path() / "korre_test_queue";
    std::filesystem::create_directories(dir);
    {
        std::ofstream list(dir / "list.txt");
        list << "one.flac\r\n\n/abs/two.mp3\nsub/three.wav  \n";
    }
    play_queue p;
    CHECK(p.add(dir / "list.txt") == 3);
    CHECK(p.upcoming()[0].path == dir / "one.flac");
    CHECK(p.upcoming()[1].path == "/abs/two.mp3");
    CHECK(p.upcoming()[2].path == dir / "sub/three.wav");
    CHECK(p.add(dir / "no_such_list.txt") == 0);
    std::filesystem::remove_all(dir);
}

} // namespace

int main()
{
    test_spectrum();
    test_queue();
    return check::result();
}
