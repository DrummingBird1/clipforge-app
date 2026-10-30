# utils/video/video_editor.py
#
# לוגיקה טהורה וניתנת-לבדיקה עבור my_scripts/video/video_editor.py - הסקריפט
# המרכזי לעריכה מהירה (watermark / המרה לאנכי / timelapse / קידוד יצוא).
# אותו עיקרון בדיוק כמו utils/media/timelapse.py - ffmpeg עצמו נשאר בסקריפט, כאן רק
# בניית פילטרים/גיאומטריה/ארגומנטים טהורה, כדי שאפשר לבדוק בלי להריץ ffmpeg.

# NOTE: the code now lives in focused modules (video_editor_*.py); every public/private name stays importable from here.

import hashlib  # noqa: F401
import json  # noqa: F401
import math  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
from datetime import datetime  # noqa: F401
from typing import Any, Dict, List, Optional, Tuple, Union  # noqa: F401
from utils.media.timelapse import (  # noqa: F401
    HORIZONTAL_SCALE_CHAIN,
    HORIZONTAL_SCALE_CHAIN_CUDA,
    VERTICAL_SCALE_CHAIN,
    VERTICAL_SCALE_CHAIN_CUDA,
    build_atempo_chain,
)

from utils.video.video_editor_naming import (  # noqa: F401
    OUTPUT_DIMENSIONS,
    WATERMARK_POSITIONS,
    SUPPORTED_CONTAINERS,
    DEFAULT_CONTAINER,
    _OUTPUT_TEMPLATE_SAMPLE_VALUES,
    resolve_output_filename,
    validate_output_template,
    SIG_SUBDIR,
    resolve_sig_path,
)
from utils.video.video_editor_effort import (  # noqa: F401
    EFFORT_LEVELS,
    EFFORT_NVENC_PRESET,
    resolve_auto_effort,
    CODEC_ARGS,
    VIDEO_EDITOR_PRESETS,
)
from utils.video.video_editor_fps_hdr import (  # noqa: F401
    DEFAULT_FPS,
    parse_fps_value,
    resolve_output_fps,
    HDR_TRANSFER_FUNCTIONS,
    is_hdr_source,
    is_high_bit_depth,
    get_hdr_output_args,
    HDR_TONEMAP_FILTER,
)
from utils.video.video_editor_filters_basic import (  # noqa: F401
    _escape_ffmpeg_filter_path,
    get_lut_filter,
    AUTO_LEVELS_FILTER,
    build_fps_filter,
    build_silence_removal_filters,
    NOISE_GATE_FILTER,
    build_chromakey_filters,
    get_vidstabdetect_filter,
    get_vidstabtransform_filter,
)
from utils.video.video_editor_codec_args import (  # noqa: F401
    get_codec_args,
    compute_target_bitrate_kbps,
    get_two_pass_codec_args,
)
from utils.video.video_editor_scale import (  # noqa: F401
    resolve_scale_chain,
    resolve_output_dimensions,
    ASPECT_PRESETS,
    RESOLUTION_SHORT_SIDE,
    SCALE_ALGORITHMS,
    FIT_MODES,
    _even,
    resolve_aspect_dimensions,
    apply_resolution_preset,
    orientation_for_dimensions,
    build_fit_scale_chain,
    apply_scale_algorithm,
    apply_pad_color,
    DENOISE_LEVELS,
    SHARPEN_LEVELS,
    TONEMAP_ALGORITHMS,
    build_tonemap_filter,
    build_eq_filter,
    build_orientation_filters,
    CUDA_ORIENTATION_DIRS,
    HYBRID_PRESCALE_MAX_RATIO,
    _even_ceil,
    build_hybrid_gpu_prefix,
    parse_cuda_filters,
    resolve_effective_output_dimensions,
    resolve_effort_thread_count,
    should_skip_scale,
)
from utils.video.video_editor_geometry import (  # noqa: F401
    resolve_trim_bounds,
    _SILENCE_START_RE,
    _SILENCE_END_RE,
    parse_silence_intervals,
    compute_silence_trim_bounds,
    _resolve_position_xy,
    compute_watermark_geometry,
    compute_removal_region,
    parse_region_fractions,
    compute_custom_removal_region,
)
from utils.video.video_editor_filtergraph import (  # noqa: F401
    LOUDNORM_FILTER,
    LOUDNORM_STATS,
    loudnorm_output_lufs,
    loudnorm_target_lufs,
    DENOISE_FILTER,
    SHARPEN_FILTER,
    DEFAULT_BACKGROUND_BLUR_SIGMA,
    _DRAWTEXT_POSITION_EXPR,
    build_drawtext_filter,
    build_edit_filter_complex,
    compute_xfade_offsets,
    build_concat_transitions_filter_complex,
)
from utils.video.video_editor_batch import (  # noqa: F401
    _TIME_TEXT_RE,
    parse_time_seconds,
    BATCH_OVERRIDE_ALLOWED_FIELDS,
    sanitize_batch_overrides,
    compute_render_signature,
)
