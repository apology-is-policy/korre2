// The parts of the player that have no interface code in them: the spectrum display's numbers and
// the play queue.

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <numbers>
#include <string>
#include <vector>

#include "braille.h"
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
    // The points run from 20 Hz to 20 kHz in even steps of pitch.
    {
        const spectrum s(100);
        CHECK(s.columns() == 100);
        CHECK(s.column_of(20.0) == 0);
        CHECK(s.column_of(19999.0) == 99);
        CHECK(s.column_of(5.0) == 0 && s.column_of(30000.0) == 99);
        CHECK(s.column_of(632.5) == 50); // the geometric middle of 20 Hz and 20 kHz
        CHECK(s.column_of(200.0) == 33 && s.column_of(2000.0) == 66);
        CHECK(spectrum().columns() == 152); // two per character cell of the player's box
    }

    for (const double rate : {44100.0, 48000.0, 96000.0})
    {
        spectrum s;
        s.set_sample_rate(rate);
        const std::string at = " at " + std::to_string(static_cast<int>(rate));

        // The treble is analysed from a few milliseconds of sound and the bass from much more, each
        // point from the shortest stretch that still resolves it.
        CHECK_MSG(s.window_seconds(s.column_of(15000)) < 0.012, "treble window" + at);
        CHECK_MSG(s.window_seconds(s.column_of(40)) > 0.15 && s.window_seconds(s.column_of(40)) < 0.4, "bass window" + at);
        for (int c = 1; c < s.columns(); ++c)
        {
            CHECK_MSG(s.window_seconds(c) <= s.window_seconds(c - 1), "windows shorten towards the treble" + at);
        }
        CHECK_MSG(s.window_seconds(s.column_of(1000)) < 0.06, "1 kHz window" + at);

        for (const double hz : {50.0, 100.0, 440.0, 1000.0, 3000.0, 10000.0})
        {
            s.clear();
            s.feed(sine(hz, 0.5, rate, static_cast<std::size_t>(rate))); // one second
            s.update();

            // The strongest point is the tone's, and it reads the tone's level (-6 dB for amplitude
            // 0.5), a little less where the tone falls between two points.
            int strongest = 0;
            for (int c = 1; c < s.columns(); ++c)
            {
                if (s.column_db(c) > s.column_db(strongest))
                {
                    strongest = c;
                }
            }
            const std::string what = std::to_string(static_cast<int>(hz)) + " Hz" + at;
            CHECK_MSG(std::abs(strongest - s.column_of(hz)) <= 1, what + ": strongest point " + std::to_string(strongest));
            CHECK_MSG(s.column_db(strongest) < -6.02 + 0.2 && s.column_db(strongest) > -6.02 - 3.0,
                      what + ": reads " + std::to_string(s.column_db(strongest)) + " dB");
            // Far from the tone there is nothing: the window keeps it from smearing.
            const int far = s.column_of(hz) > s.columns() / 2 ? s.columns() / 10 : s.columns() * 9 / 10;
            CHECK_MSG(s.column_db(far) < -80.0, what + ": far point " + std::to_string(s.column_db(far)) + " dB");
            // What is plotted is that level on the display's scale.
            const float plotted = s.values()[static_cast<std::size_t>(strongest)];
            const double expected = (s.column_db(strongest) - spectrum::floor_db) / (spectrum::top_db - spectrum::floor_db);
            CHECK_NEAR(plotted, std::clamp(expected, 0.0, 1.0), 1e-5);
        }

        // White noise has the same power in every Hz, so on points that are each a fixed fraction of
        // an octave wide it rises 3 dB per octave, evenly: the windows change length along the way
        // and that must not show as steps or as a tilt.
        {
            s.clear();
            std::vector<double> sum(static_cast<std::size_t>(s.columns()), 0.0);
            std::uint64_t state = 0x9E3779B97F4A7C15ull;
            const int rounds = 400;
            std::vector<float> block(static_cast<std::size_t>(rate / 50.0));
            for (int r = 0; r < rounds + 50; ++r)
            {
                for (float& v : block)
                {
                    state = state * 6364136223846793005ull + 1442695040888963407ull;
                    v = static_cast<float>(static_cast<double>(static_cast<std::int32_t>(state >> 32)) / 2147483648.0 * 0.1);
                }
                s.feed(block);
                s.update();
                if (r >= 50)
                {
                    for (int c = 0; c < s.columns(); ++c)
                    {
                        sum[static_cast<std::size_t>(c)] += std::pow(10.0, s.column_db(c) / 10.0);
                    }
                }
            }
            // From 250 Hz up every point has a band of its own. Its level against the band's width:
            const double ratio = std::pow(spectrum::high_hz / spectrum::low_hz, 1.0 / s.columns());
            const auto density_db = [&](int c) {
                const double width_hz = spectrum::low_hz * std::pow(ratio, c) * (ratio - 1.0);
                return 10 * std::log10(sum[static_cast<std::size_t>(c)] / rounds / width_hz);
            };
            // amplitude 0.1, uniform: power 0.01 / 3 spread over half the sample rate, against a sine's 0.5
            const double expected = 10 * std::log10(0.01 / 3.0 / (rate / 2.0) / 0.5);
            const int from = s.column_of(250), to = s.column_of(16000);
            double worst = 0, step = 0;
            for (int c = from; c <= to; ++c)
            {
                worst = std::max(worst, std::fabs(density_db(c) - expected));
                if (c > from)
                {
                    step = std::max(step, std::fabs(density_db(c) - density_db(c - 1)));
                }
            }
            CHECK_MSG(worst < 1.0, "white noise reads its level in every band" + at + ": off by up to " + std::to_string(worst) + " dB");
            CHECK_MSG(step < 0.7, "no steps between neighbouring points" + at + ": " + std::to_string(step) + " dB");
        }
    }

    // No hold: the treble follows the sound within a frame, and with no sound everything is at zero.
    spectrum s;
    s.set_sample_rate(48000);
    const int treble = s.column_of(10000), bass = s.column_of(50);
    std::vector<float> both = sine(10000, 0.25, 48000, 48000);
    const std::vector<float> low = sine(50, 0.25, 48000, 48000);
    for (std::size_t i = 0; i < both.size(); ++i)
    {
        both[i] += low[i];
    }
    s.feed(both);
    s.update();
    CHECK(s.values()[static_cast<std::size_t>(treble)] > 0.9f && s.values()[static_cast<std::size_t>(bass)] > 0.9f);
    s.feed(std::vector<float>(480, 0.0f)); // 10 ms of silence
    s.update();
    const float falling = s.values()[static_cast<std::size_t>(treble)];
    CHECK_MSG(falling > 0.3f && falling < 0.99f, "10 ms after the sound stopped the treble shows what was left of it in that time");
    s.feed(std::vector<float>(960, 0.0f));
    s.update();
    CHECK_MSG(s.values()[static_cast<std::size_t>(treble)] == 0.0f, "30 ms after the sound stopped the treble is at zero");
    CHECK_MSG(s.values()[static_cast<std::size_t>(bass)] > 0.8f, "while the bass, analysed over a sixth of a second, is still falling");
    s.feed(std::vector<float>(9600, 0.0f));
    s.update();
    CHECK(s.values()[static_cast<std::size_t>(bass)] == 0.0f);
    s.feed(both);
    s.clear();
    s.update();
    CHECK(s.values()[static_cast<std::size_t>(treble)] == 0.0f && s.values()[static_cast<std::size_t>(bass)] == 0.0f);
}

void test_braille()
{
    const auto cell = [](const std::string& line, std::size_t index) -> unsigned {
        // The index-th character of a line of spaces and three-byte Braille characters, as its dot bits.
        std::size_t at = 0;
        for (std::size_t i = 0; i < index; ++i)
        {
            at += line[at] == ' ' ? 1 : 3;
        }
        if (line[at] == ' ')
        {
            return 0;
        }
        const unsigned code = (static_cast<unsigned>(static_cast<unsigned char>(line[at]) & 0x0F) << 12) |
                              (static_cast<unsigned>(static_cast<unsigned char>(line[at + 1]) & 0x3F) << 6) |
                              static_cast<unsigned>(static_cast<unsigned char>(line[at + 2]) & 0x3F);
        return code - 0x2800;
    };

    // Four points on two rows: zero is the bottom dot row, one the top.
    {
        const std::vector<float> v = {0.0f, 0.0f, 1.0f, 1.0f};
        const auto lines = braille_curve(v, 2);
        CHECK(lines.size() == 2);
        CHECK(cell(lines[1], 0) == (0x40u | 0x80u)); // both bottom dots of the first cell
        CHECK(cell(lines[0], 0) == 0u);
        // The second cell: its left column carries the whole rise (the step is drawn in the later
        // point's column, stopping short of the earlier point's dot), its right column the top dot.
        CHECK(cell(lines[0], 1) == (0x01u | 0x02u | 0x04u | 0x40u | 0x08u));
        CHECK(cell(lines[1], 1) == (0x01u | 0x02u | 0x04u));
    }
    // A level line in the middle of one row, and values outside 0..1 clamped.
    {
        const std::vector<float> v = {2.0f, -1.0f};
        const auto lines = braille_curve(v, 1);
        CHECK(lines.size() == 1);
        CHECK(cell(lines[0], 0) == (0x01u | 0x10u | 0x20u | 0x80u)); // top left; right column from below the top down
    }
    // Every line has one character per two points, an odd count rounded up.
    {
        const std::vector<float> v(151, 0.5f);
        const auto lines = braille_curve(v, 17);
        CHECK(lines.size() == 17);
        for (const std::string& line : lines)
        {
            std::size_t chars = 0;
            for (std::size_t at = 0; at < line.size(); at += line[at] == ' ' ? 1 : 3)
            {
                ++chars;
            }
            CHECK(chars == 76);
        }
        // 0.5 of 67 dot rows up from the bottom: dot row 67 - 34 = 33 from the top, row 8 of 17, second dot row
        CHECK(cell(lines[8], 10) == (0x02u | 0x10u));
        CHECK(cell(lines[7], 10) == 0u && cell(lines[9], 10) == 0u);
    }
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
    test_braille();
    test_queue();
    return check::result();
}
