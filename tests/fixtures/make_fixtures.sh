#!/bin/sh
# Regenerates the test files in this directory. Needs ffmpeg with libmp3lame.
#
# Every file holds the same known signal, so a test can check decoded samples against the formula:
#   left  = 0.5  * sin(2 pi  441 t)
#   right = 0.25 * cos(2 pi 1000 t)
# The mono files hold the left signal. ffmpeg is the writer on purpose: the decoders are then tested
# against files made by an independent program, not by korre's own writers.
set -e
cd "$(dirname "$0")"

STEREO="aevalsrc=exprs='0.5*sin(2*PI*441*t)|0.25*cos(2*PI*1000*t)'"
MONO="aevalsrc=exprs='0.5*sin(2*PI*441*t)'"
FF="ffmpeg -hide_banner -loglevel error -y -f lavfi"

$FF -i "$STEREO:sample_rate=44100:duration=0.2" -c:a pcm_s16le tone_s16.wav          # has a LIST chunk before the audio
$FF -i "$STEREO:sample_rate=44100:duration=0.2" -c:a pcm_s24le tone_s24.wav          # "extensible" header
$FF -i "$STEREO:sample_rate=96000:duration=0.05" -c:a pcm_s32le tone_s32_96k.wav
$FF -i "$STEREO:sample_rate=48000:duration=0.1" -c:a pcm_f32le tone_f32_48k.wav
$FF -i "$MONO:sample_rate=44100:duration=0.2" -c:a pcm_u8 tone_u8_mono.wav
$FF -i "$MONO:sample_rate=44100:duration=0.2" -c:a pcm_s16le tone_s16_mono.wav
$FF -i "$STEREO:sample_rate=44100:duration=0.5" -c:a flac -sample_fmt s16 tone_s16.flac
$FF -i "$STEREO:sample_rate=96000:duration=0.25" -c:a flac -sample_fmt s32 -bits_per_raw_sample 24 tone_s24_96k.flac
$FF -i "$MONO:sample_rate=44100:duration=0.5" -c:a flac -sample_fmt s16 tone_s16_mono.flac
$FF -i "$STEREO:sample_rate=44100:duration=1" -c:a libmp3lame -b:a 192k tone.mp3
$FF -i "$MONO:sample_rate=44100:duration=1" -c:a libmp3lame -b:a 96k tone_mono.mp3

# Broken files the readers must refuse or survive
head -c 2000 tone_s16.wav > cut_short.wav        # the header promises more audio than there is
printf 'this is not audio at all, just text\n' > not_audio.wav
head -c 30 tone_s16.wav > header_only.wav
