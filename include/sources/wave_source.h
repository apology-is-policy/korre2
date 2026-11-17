#pragma once

#include <vector>

#include "sampler.h"
#include "sources/wave.h"

class wave_source : public sampler
{
public:
    wave *w;

    explicit wave_source(wave *w, uint32_t sample_rate);
    ~wave_source() override;

    virtual std::tuple<double, double> sample(size_t t) override;
    virtual size_t sample_size() override;
    virtual void pulse() override;
};