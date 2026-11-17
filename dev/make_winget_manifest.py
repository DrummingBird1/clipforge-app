# dev/make_winget_manifest.py
#
# 16.11.2026 (ClipForge 2.0): שלושת קובצי ה-manifest של winget (version, installer, locale) לגרסה שיצאה - מה-zip ומה-SHA-256
# שב-Release. הפלט: build/winget/manifests/d/DrummingBird1/ClipForge/<גרסה>/ - בדיוק המבנה של microsoft/winget-pkgs.
# לא שולח כלום: בדיקה ב-`winget validate <תיקייה>`, והגשת ה-PR ל-winget-pkgs ידנית (פומבית - רק באישור הבעלים).
#
#   uv run python dev/make_winget_manifest.py --version 2.0.0 --sha256 <hash>
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ID = "DrummingBird1.ClipForge"
PUBLISHER = "DrummingBird1"
REPO_URL = "https://github.com/DrummingBird1/clipforge-app"
MANIFEST_VERSION = "1.10.0"


def installer_url(version):
    return f"{REPO_URL}/releases/download/v{version}/ClipForge-{version}-win64.zip"


def manifests(version, sha256):
    head = f"PackageIdentifier: {PACKAGE_ID}\nPackageVersion: {version}\n"
    tail = f"ManifestVersion: {MANIFEST_VERSION}\n"
    return {
        f"{PACKAGE_ID}.yaml": (f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.{MANIFEST_VERSION}.schema.json\n"
                               + head + "DefaultLocale: en-US\nManifestType: version\n" + tail),
        f"{PACKAGE_ID}.installer.yaml": (
            f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.{MANIFEST_VERSION}.schema.json\n" + head
            + "InstallerType: zip\nNestedInstallerType: portable\nNestedInstallerFiles:\n"
            + f"- RelativeFilePath: ClipForge-{version}-win64\\ClipForge.exe\n  PortableCommandAlias: clipforge\n"
            + "ArchiveBinariesDependOnPath: true\nInstallers:\n- Architecture: x64\n"
            + f"  InstallerUrl: {installer_url(version)}\n  InstallerSha256: {sha256.upper()}\n"
            + "ManifestType: installer\n" + tail),
        f"{PACKAGE_ID}.locale.en-US.yaml": (
            f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.{MANIFEST_VERSION}.schema.json\n" + head
            + f"PackageLocale: en-US\nPublisher: {PUBLISHER}\nPublisherUrl: https://github.com/{PUBLISHER}\n"
            + f"PackageName: ClipForge\nPackageUrl: {REPO_URL}\nLicense: MIT\nLicenseUrl: {REPO_URL}/blob/main/LICENSE\n"
            + "ShortDescription: Record, edit and publish gameplay clips and data videos - a local video studio in the browser.\n"
            + "Tags:\n- video\n- video-editor\n- gaming\n- shorts\n- obs\n- ffmpeg\n"
            + f"ReleaseNotesUrl: {REPO_URL}/releases/tag/v{version}\n"
            + "ManifestType: defaultLocale\n" + tail),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="manifests של winget לגרסה שיצאה")
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256", required=True, help="ה-SHA-256 של ה-zip (מ-SHA256SUMS.txt ב-Release)")
    parser.add_argument("--out", default=os.path.join(ROOT, "build", "winget"))
    args = parser.parse_args(argv)
    if len(args.sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in args.sha256):
        raise SystemExit("SHA-256 לא תקין")
    folder = os.path.join(args.out, "manifests", "d", "DrummingBird1", "ClipForge", args.version)
    os.makedirs(folder, exist_ok=True)
    for name, text in manifests(args.version, args.sha256).items():
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(f"{folder}\n  winget validate \"{folder}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
