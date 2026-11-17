#include "tape/profile.h"

#include <cmath>
#include <fstream>
#include <sstream>

#include <nlohmann/json.hpp>

namespace tape
{
namespace
{

using json = nlohmann::json;

/// Thrown inside the parser, turned into the error string at the boundary.
struct profile_error
{
    std::string what;
};

const json& member(const json& object, const char* key, const std::string& where)
{
    if (!object.is_object() || !object.contains(key))
    {
        throw profile_error{"missing \"" + where + key + "\""};
    }
    return object.at(key);
}

double number(const json& object, const char* key, const std::string& where)
{
    const json& v = member(object, key, where);
    if (!v.is_number())
    {
        throw profile_error{"\"" + where + key + "\" is not a number"};
    }
    const double d = v.get<double>();
    if (!std::isfinite(d))
    {
        throw profile_error{"\"" + where + key + "\" is not finite"};
    }
    return d;
}

std::vector<double> table(const json& object, const char* key, const std::string& where)
{
    const json& v = member(object, key, where);
    if (!v.is_array())
    {
        throw profile_error{"\"" + where + key + "\" is not a list"};
    }
    std::vector<double> out;
    out.reserve(v.size());
    for (const json& e : v)
    {
        if (!e.is_number() || !std::isfinite(e.get<double>()))
        {
            throw profile_error{"\"" + where + key + "\" holds something that is not a finite number"};
        }
        out.push_back(e.get<double>());
    }
    return out;
}

stereo left_right(const json& object, const char* key, const std::string& where)
{
    const json& v = member(object, key, where);
    return {number(v, "L", where + key + "."), number(v, "R", where + key + ".")};
}

void same_length(const std::vector<double>& a, const std::vector<double>& b, const std::string& what)
{
    if (a.size() != b.size())
    {
        throw profile_error{what + ": tables of different lengths (" + std::to_string(a.size()) + " and " + std::to_string(b.size()) + ")"};
    }
}

void ascending(const std::vector<double>& f, std::size_t at_least, bool positive, const std::string& what)
{
    if (f.size() < at_least)
    {
        throw profile_error{what + ": needs at least " + std::to_string(at_least) + " points"};
    }
    for (std::size_t i = 0; i < f.size(); ++i)
    {
        if ((i > 0 && f[i] <= f[i - 1]) || (positive && f[i] <= 0))
        {
            throw profile_error{what + ": frequencies must be " + (positive ? "positive and " : "") + "ascending"};
        }
    }
}

void non_negative(const std::vector<double>& v, const std::string& what)
{
    for (const double x : v)
    {
        if (x < 0)
        {
            throw profile_error{what + ": negative value"};
        }
    }
}

profile build(const json& j)
{
    profile p;
    p.version = static_cast<int>(number(j, "version", ""));
    if (p.version != 2)
    {
        throw profile_error{"profile version " + std::to_string(p.version) + " is not supported (this engine reads version 2)"};
    }
    if (j.contains("name") && j.at("name").is_string())
    {
        p.name = j.at("name").get<std::string>();
    }
    p.gain_db = left_right(j, "gain_db", "");
    p.delay_us = left_right(j, "delay_us", "");
    if (j.contains("polarity"))
    {
        const double pol = number(j, "polarity", "");
        if (pol != 1 && pol != -1)
        {
            throw profile_error{"\"polarity\" must be 1 or -1"};
        }
        p.polarity = static_cast<int>(pol);
    }

    {
        const json& eq = member(j, "eq", "");
        p.eq.freqs = table(eq, "freqs", "eq.");
        p.eq.db = {table(eq, "L", "eq."), table(eq, "R", "eq.")};
        p.eq.phase = {table(eq, "phase_L", "eq."), table(eq, "phase_R", "eq.")};
        ascending(p.eq.freqs, 13, true, "eq"); // the extrapolation rules look 12 points in from the low end
        for (int c = 0; c < 2; ++c)
        {
            same_length(p.eq.freqs, p.eq.db[c], "eq");
            same_length(p.eq.freqs, p.eq.phase[c], "eq");
        }
    }
    {
        const json& hiss = member(j, "hiss", "");
        p.hiss.freqs = table(hiss, "freqs", "hiss.");
        p.hiss.psd = {table(hiss, "L", "hiss."), table(hiss, "R", "hiss.")};
        ascending(p.hiss.freqs, 2, false, "hiss");
        for (int c = 0; c < 2; ++c)
        {
            same_length(p.hiss.freqs, p.hiss.psd[c], "hiss");
            non_negative(p.hiss.psd[c], "hiss");
        }
    }
    {
        const json& tr = member(j, "transport", "");
        p.transport.freqs = table(tr, "freqs", "transport.");
        p.transport.psd_us2_per_hz = table(tr, "psd_us2_per_hz", "transport.");
        p.transport.crossover_hz = number(tr, "crossover_hz", "transport.");
        ascending(p.transport.freqs, 2, false, "transport");
        same_length(p.transport.freqs, p.transport.psd_us2_per_hz, "transport");
        non_negative(p.transport.psd_us2_per_hz, "transport");

        const json& df = member(j, "differential", "");
        p.differential.freqs = table(df, "freqs", "differential.");
        p.differential.psd_us2_per_hz = table(df, "psd_us2_per_hz", "differential.");
        ascending(p.differential.freqs, 2, false, "differential");
        same_length(p.differential.freqs, p.differential.psd_us2_per_hz, "differential");
        non_negative(p.differential.psd_us2_per_hz, "differential");
    }
    {
        const json& jt = member(j, "jitter", "");
        p.jitter.freqs = table(jt, "freqs", "jitter.");
        p.jitter.psd_common_us2_per_hz = table(jt, "psd_common_us2_per_hz", "jitter.");
        p.jitter.psd_indep_us2_per_hz = table(jt, "psd_indep_us2_per_hz", "jitter.");
        ascending(p.jitter.freqs, 2, true, "jitter");
        same_length(p.jitter.freqs, p.jitter.psd_common_us2_per_hz, "jitter");
        same_length(p.jitter.freqs, p.jitter.psd_indep_us2_per_hz, "jitter");
        non_negative(p.jitter.psd_common_us2_per_hz, "jitter");
        non_negative(p.jitter.psd_indep_us2_per_hz, "jitter");
    }
    {
        const json& fl = member(j, "flicker", "");
        p.flicker.rate_freqs = table(fl, "rate_freqs", "flicker.");
        p.flicker.rate_psd = table(fl, "rate_psd", "flicker.");
        p.flicker.depth_freqs = table(fl, "depth_freqs", "flicker.");
        p.flicker.depth_common = table(fl, "depth_common", "flicker.");
        p.flicker.depth_indep = table(fl, "depth_indep", "flicker.");
        ascending(p.flicker.rate_freqs, 2, true, "flicker rate");
        same_length(p.flicker.rate_freqs, p.flicker.rate_psd, "flicker rate");
        non_negative(p.flicker.rate_psd, "flicker rate");
        ascending(p.flicker.depth_freqs, 2, true, "flicker depth");
        same_length(p.flicker.depth_freqs, p.flicker.depth_common, "flicker depth");
        same_length(p.flicker.depth_freqs, p.flicker.depth_indep, "flicker depth");
        non_negative(p.flicker.depth_common, "flicker depth");
        non_negative(p.flicker.depth_indep, "flicker depth");
    }
    {
        const json& dr = member(j, "dropouts", "");
        p.dropouts.rate_per_min = number(dr, "rate_per_min", "dropouts.");
        for (const json& e : member(dr, "events", "dropouts."))
        {
            profile::dropout_event ev;
            ev.depth_db = number(e, "depth_db", "dropouts.events.");
            ev.dur_ms = number(e, "dur_ms", "dropouts.events.");
            ev.both = member(e, "both", "dropouts.events.").get<bool>();
            p.dropouts.events.push_back(ev);
        }
        if (p.dropouts.rate_per_min < 0)
        {
            throw profile_error{"dropouts: negative rate"};
        }
    }
    {
        const json& sat = member(j, "saturation", "");
        p.saturation.cubic_rel_db = number(sat, "cubic_rel_db", "saturation.");
        if (!member(sat, "ref_rms_dbfs", "saturation.").is_null())
        {
            p.saturation.ref_rms_dbfs = number(sat, "ref_rms_dbfs", "saturation.");
        }
        if (sat.contains("hf") && !sat.at("hf").is_null())
        {
            const json& hf = sat.at("hf");
            profile::treble_saturation t;
            t.tau_s = number(hf, "tau_s", "saturation.hf.");
            t.shelf_db = number(hf, "shelf_db", "saturation.hf.");
            t.c = number(hf, "c", "saturation.hf.");
            if (t.tau_s <= 0)
            {
                throw profile_error{"saturation.hf: the time constant must be positive"};
            }
            p.saturation.hf = t;
        }
    }
    if (j.contains("tones"))
    {
        for (const json& e : j.at("tones"))
        {
            profile::tone t;
            t.hz = number(e, "hz", "tones.");
            t.dbfs = {number(e, "L_dbfs", "tones."), number(e, "R_dbfs", "tones.")};
            t.phase_deg = number(e, "phase_deg", "tones.");
            p.tones.push_back(t);
        }
    }
    return p;
}

} // namespace

std::expected<profile, std::string> parse_profile(std::string_view text)
{
    // No exceptions from the JSON library: a parse error comes back as a "discarded" value.
    const json j = json::parse(text, nullptr, false);
    if (j.is_discarded())
    {
        return std::unexpected("not valid JSON");
    }
    try
    {
        return build(j);
    }
    catch (const profile_error& e)
    {
        return std::unexpected(e.what);
    }
    catch (const json::exception& e) // a value of the wrong kind where build() reads one directly
    {
        return std::unexpected(std::string("unexpected value in the profile: ") + e.what());
    }
}

std::expected<profile, std::string> load_profile(const std::filesystem::path& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f)
    {
        return std::unexpected("cannot open " + path.string());
    }
    std::ostringstream text;
    text << f.rdbuf();
    auto p = parse_profile(text.str());
    if (!p)
    {
        return std::unexpected(path.filename().string() + ": " + p.error());
    }
    if (p->name.empty())
    {
        p->name = path.stem().string();
    }
    return p;
}

} // namespace tape
