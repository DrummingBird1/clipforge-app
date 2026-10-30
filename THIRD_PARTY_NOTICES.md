# Third-party notices

ClipForge itself is released under the MIT License (see `LICENSE`). It includes, or the portable Windows package
ships next to it, the third-party components below. Each keeps its own license; the full texts are in the files named
here, and for Python packages in each package's `*.dist-info` folder inside the portable package.

## Included in this repository

| Component | Used for | License | License text |
|---|---|---|---|
| [Heebo](https://github.com/OdedEzer/heebo) - Copyright 2014 The Heebo Project Authors | Interface font | SIL Open Font License 1.1 | `assets/fonts/OFL-Heebo.txt` |
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) - Copyright 2020 The JetBrains Mono Project Authors | Monospace font (logs) | SIL Open Font License 1.1 | `assets/fonts/OFL-JetBrainsMono.txt` |
| [Lucide](https://lucide.dev) - Copyright (c) Lucide Icons and Contributors | Interface icons | ISC | `assets/icons/LICENSE-lucide.txt` |
| [YuNet face detection model](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) (`face_detection_yunet_2023mar.onnx`) | Face-aware smart crop | Apache License 2.0 | `assets/face_detection_yunet_2023mar.LICENSE` |

## Shipped in the portable Windows package

These are not in the repository; `dev/build_portable.py` adds them to `ClipForge-<version>-win64.zip`.

- **FFmpeg** (`ffmpeg/`) - a GPLv3 build (`--enable-gpl --enable-version3`), needed for `libx264` encoding and the
  `vidstab` stabilization filter. ClipForge runs it as a separate program and does not link to it, so ClipForge stays
  MIT. The build's license and the link to its exact source are in `ffmpeg/LICENSE` and `ffmpeg/README.txt` inside the
  package; FFmpeg's source is at https://ffmpeg.org/download.html.
- **Python** (`python/`) - the CPython runtime, Python Software Foundation License Version 2 (`python/LICENSE.txt`).
- **Python packages** (`python/Lib/site-packages/`) - the runtime dependencies locked in `uv.lock`, without the
  development group. Their licenses, as declared in each package's metadata:

| Package | Version | License |
|---|---|---|
| aiohappyeyeballs | 2.7.1 | Python Software Foundation License |
| aiohttp | 3.14.4 | Apache-2.0 AND MIT |
| aiosignal | 1.4.0 | Apache Software License |
| aiosqlite | 0.22.1 | MIT License |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| audioop-lts | 0.2.2 | PSF-2.0 |
| av | 19.0.1 | BSD-3-Clause |
| certifi | 2026.10.19 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| contourpy | 1.4.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| ctranslate2 | 4.8.2 | MIT |
| customtkinter | 6.0.0 | MIT License |
| cycler | 0.12.1 | BSD License |
| darkdetect | 0.8.0 | BSD License |
| Deprecated | 3.0.0 | MIT |
| discord.py | 2.7.1 | MIT License |
| distro | 1.9.0 | Apache Software License |
| et_xmlfile | 2.0.0 | MIT License |
| fastapi | 0.143.0 | MIT |
| faster-whisper | 1.2.1 | MIT License |
| feedparser | 6.0.14 | BSD-2-Clause |
| feedparser-sgmllib | 2.1.0 | PSF-2.0 |
| filelock | 4.1.0 | MIT |
| flatbuffers | 25.12.19 | Apache Software License |
| fonttools | 4.66.1 | MIT |
| frozenlist | 1.8.0 | Apache-2.0 |
| fsspec | 2026.9.0 | BSD-3-Clause |
| google-api-core | 2.42.0 | Apache Software License |
| google-api-python-client | 2.201.0 | Apache Software License |
| google-auth | 2.61.0 | Apache Software License |
| google-auth-httplib2 | 0.4.4 | Apache Software License |
| google-auth-oauthlib | 1.5.0 | Apache Software License |
| google-genai | 2.29.0 | Apache-2.0 |
| googleapis-common-protos | 1.75.5 | Apache-2.0 |
| h11 | 0.16.0 | MIT License |
| hf-xet | 1.7.0 | Apache-2.0 |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httplib2 | 0.32.0 | MIT License |
| httpx | 0.28.1 | BSD License |
| httpx2 | 2.13.1 | BSD-3-Clause |
| huggingface_hub | 2.2.0 | Apache Software License |
| idna | 3.20 | BSD-3-Clause |
| jaraco.classes | 3.4.0 | MIT License |
| jaraco.context | 6.1.2 | MIT |
| jaraco.functools | 4.6.0 | MIT |
| keyboard | 0.13.5 | MIT License |
| keyring | 25.7.0 | MIT |
| kiwisolver | 1.5.1 | BSD License |
| limits | 5.8.0 | MIT |
| matplotlib | 3.11.2 | Python Software Foundation License |
| more-itertools | 11.1.0 | MIT |
| msgpack | 1.2.3 | Apache-2.0 |
| multidict | 6.9.1 | Apache License 2.0 |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| oauthlib | 4.0.0 | BSD-3-Clause |
| onnxruntime | 1.31.0 | MIT License |
| opencv-python | 5.0.0.93 | Apache Software License |
| openpyxl | 3.1.5 | MIT License |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pandas | 3.0.6 | BSD License |
| pillow | 13.0.0 | MIT-CMU |
| propcache | 0.5.4 | Apache-2.0 |
| proto-plus | 1.29.0 | Apache Software License |
| protobuf | 7.36.2 | 3-Clause BSD License |
| psutil | 7.2.2 | BSD-3-Clause |
| pyasn1 | 0.6.4 | BSD-2-Clause |
| pyasn1_modules | 0.4.2 | BSD License |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.0 | MIT |
| pydantic_core | 2.50.0 | MIT |
| pydub | 0.25.1 | MIT License |
| pyparsing | 3.3.3 | MIT |
| pyperclip | 1.11.0 | BSD License |
| pystray | 0.19.5 | GNU Lesser General Public License v3 (LGPLv3) |
| pytesseract | 0.3.13 | Apache Software License |
| python-dateutil | 2.9.0.post0 | BSD License; Apache Software License |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT License |
| qrcode | 8.2 | BSD-3-Clause |
| requests | 2.34.2 | Apache Software License |
| requests-oauthlib | 2.0.0 | BSD License |
| Send2Trash | 2.1.0 | BSD-3-Clause |
| simpleobsws | 1.4.3 | MIT License |
| six | 1.17.0 | MIT License |
| slowapi | 0.1.10 | MIT License |
| sniffio | 1.3.1 | MIT License; Apache Software License |
| starlette | 1.7.0 | BSD-3-Clause |
| tenacity | 9.1.4 | Apache Software License |
| tkinterdnd2 | 0.6.3 | MIT License |
| tokenizers | 0.23.3 | Apache Software License |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| truststore | 0.10.4 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.5 | Apache-2.0 |
| uritemplate | 4.2.0 | BSD 3-Clause OR Apache-2.0 |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| websockets | 16.1.1 | BSD-3-Clause |
| winotify | 1.1.0 | MIT License |
| wrapt | 2.5.0 | BSD-2-Clause |
| yarl | 1.25.1 | Apache-2.0 |

### Copyleft components, and what that means here

- **certifi** - Mozilla Public License 2.0 (MPL 2.0). Shipped unmodified as a separate Python package; its source is on PyPI and its license is in
  its `dist-info` folder. You may replace it with another version of the package.
- **pystray** - GNU Lesser General Public License v3 (LGPLv3). Shipped unmodified as a separate Python package; its source is on PyPI and its license is in
  its `dist-info` folder. You may replace it with another version of the package.
- **tqdm** - MPL-2.0 AND MIT. Shipped unmodified as a separate Python package; its source is on PyPI and its license is in
  its `dist-info` folder. You may replace it with another version of the package.
- **pyautogui** and its dependencies **MouseInfo** and **PyMsgBox** (GPLv3+), **PyScreeze**, **pytweening**,
  **PyGetWindow** and **PyRect** are listed in `pyproject.toml` for a developer tool (`my_scripts/tools/check_pos.py`)
  and are **not** shipped in the portable package.

Models that ClipForge downloads at run time (for example Whisper speech-to-text models from Hugging Face) are not
included in either; they come with their own licenses from their publishers.
