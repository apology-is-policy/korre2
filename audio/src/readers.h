#pragma once

// The three decoders behind open_audio().

#include "korre/audio_file.h"

namespace korre::detail
{

using reader_result = std::expected<std::unique_ptr<audio_reader>, std::string>;

reader_result open_wav(const std::filesystem::path& path);
reader_result open_flac(const std::filesystem::path& path);
reader_result open_mp3(const std::filesystem::path& path);

} // namespace korre::detail
