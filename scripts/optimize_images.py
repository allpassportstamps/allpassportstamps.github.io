#!/usr/bin/env python3
"""Prepare static blog images offline. Originals are never modified."""

import argparse
import hashlib
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, unquote

from PIL import Image, ImageCms, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {"version": 1, "long_edge": 1600, "thumbnail_width": 800, "quality": 82}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
BEGIN = "# BEGIN generated image exclusions"
END = "# END generated image exclusions"
IMAGE = r'!\[(?P<alt>[^\]\n]*)\]\((?P<url>[^)]+)\)(?:\{:(?P<attrs>[^}\n]*)\})?'
TOKEN = re.compile(
    r'(?P<skip><!--.*?-->|{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|'
    r'(?P<fence>^```[^\n]*\n.*?^```[^\n]*$|^~~~[^\n]*\n.*?^~~~[^\n]*$)|`[^`\n]*`)'
    r'|(?P<include>{%\s*include\s+image.html\s+.*?%})|(?P<image>' + IMAGE + r')',
    re.DOTALL | re.MULTILINE,
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_changed(path, content):
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)
    return True


def source_key(url):
    url = re.sub(r'^{{\s*site.baseurl\s*}}', '', url.strip())
    if not url.startswith("/assets/img/"):
        return None
    key = unquote(url[len("/assets/img/"):])
    if ".." in Path(key).parts or Path(key).is_absolute():
        raise ValueError(f"Unsafe image path: {url}")
    return key


def scalar(text, name):
    match = re.search(r'^' + re.escape(name) + r':\s*([^\n]*)$', text, re.MULTILINE)
    if not match:
        return None
    return match[1].split(" #", 1)[0].strip().strip("\"'") or None


def documents(root):
    return sorted(p for folder in ("_posts", "_pages") for p in (root / folder).rglob("*")
                  if p.suffix.lower() in {".md", ".markdown", ".html"})


def prepare_document(path, text, available, root):
    """Convert only supported photo markup; retain comments, code and source identifiers."""
    count = 0
    referenced = set()

    def convert(match):
        nonlocal count
        if match["skip"]:
            return match[0]
        if match["include"]:
            src = re.search(r'\bsrc="([^"]+)"', match[0])
            if not src:
                raise ValueError(f"{path}: image include needs a quoted src")
            key = html.unescape(src[1])
            if key not in available:
                raise ValueError(f"{path}: missing or unsupported original: {key}")
            referenced.add(key)
            count += 1
            return match[0]
        key = source_key(match["url"])
        if key is None or Path(key).suffix.lower() not in PHOTO_EXTENSIONS:
            return match[0]
        if key.startswith(("flags/", "favicon/")):
            return match[0]
        if key not in available:
            raise ValueError(f"{path}: missing or unsupported original: {key}")
        # Animated PNGs are deliberately left in their original format and markup.
        if available[key].get("animated"):
            return match[0]
        attrs = match["attrs"] or ""
        width = re.fullmatch(r'\s*width="(\d+(?:\.\d+)?%)"\s*', attrs) if attrs else None
        if attrs and not width:
            raise ValueError(f"{path}: unsupported image attributes: {attrs}")
        if '"' in key or "{%" in key or "{{" in key:
            raise ValueError(f"{path}: unsupported characters in image filename: {key}")
        referenced.add(key)
        count += 1
        alt = html.escape(match["alt"], quote=True)
        if "{%" in alt or "{{" in alt:
            raise ValueError(f"{path}: Liquid expressions in image alt text are unsupported")
        parameters = f'src="{key}" alt="{alt}"'
        if width:
            parameters += f' width="{width[1]}"'
        if count <= 2:
            parameters += ' loading="eager"'
        return "{% include image.html " + parameters + " %}"

    result = TOKEN.sub(convert, text)
    # Do not exclude originals still referenced by unrecognized HTML/Markdown.
    remainder = TOKEN.sub("", result)
    for match in re.finditer(r'/assets/img/([^<>]+)', remainder):
        if re.search(r'\.(?:jpe?g|png)\b', match[1], re.IGNORECASE):
            if not match[1].startswith(("flags/", "favicon/")):
                raise ValueError(f"{path}: unsupported original image markup near {match[0][:100]}")
    return result, referenced


def render_image(source, destination, *, thumbnail=False):
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        transparent = has_alpha and image.convert("RGBA").getextrema()[3][0] < 255
        mode = "RGBA" if transparent else "RGB"
        if original.info.get("icc_profile"):
            image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(BytesIO(original.info["icc_profile"])),
                                             ImageCms.createProfile("sRGB"), outputMode=mode)
        else:
            image = image.convert(mode)
        if thumbnail:
            width = min(image.width, SETTINGS["thumbnail_width"])
            size = (width, max(1, round(image.height * width / image.width)))
        else:
            size = (SETTINGS["long_edge"], SETTINGS["long_edge"])
        image.thumbnail(size, Image.Resampling.LANCZOS)
        suffix = ".png" if transparent else ".jpg"
        destination = Path(str(destination) + suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        options = {"optimize": True}
        if not transparent:
            options.update(quality=SETTINGS["quality"], progressive=True)
        image.save(temporary, format="PNG" if transparent else "JPEG", **options)
        temporary.replace(destination)
        return destination, image.size


def exclusion_config(config, keys):
    # Keep user-maintained exclusions, replacing only this script's own block.
    config = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', '', config, flags=re.DOTALL)
    inline = re.search(r'^exclude: (\[.*\])\s*$', config, re.MULTILINE)
    if inline:
        exclusions = json.loads(inline[1])
        replacement = "exclude:\n" + "".join("  - " + json.dumps(item) + "\n" for item in exclusions)
        config = config[:inline.start()] + replacement + config[inline.end():]
    match = re.search(r'^exclude:\s*\n(?:[ \t]+-[^\n]*\n)*', config, re.MULTILINE)
    if not match:
        raise ValueError("_config.yml: expected an exclude list; no files were rewritten")
    generated = ["scripts", "tests", "README.md", "assets/optimized/.DS_Store"]
    generated.extend("assets/img/" + key for key in sorted(keys))
    block = BEGIN + "\n" + "".join("  - " + json.dumps(item) + "\n" for item in generated) + END + "\n"
    return config[:match.end()] + block + config[match.end():]


def run(root, dry_run=False):
    source_dir = root / "assets/img"
    manifest_path = root / "_data/images.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    config_path = root / "_config.yml"
    config = config_path.read_text()
    texts = {p: p.read_text() for p in documents(root)}
    drafts = [p for p, t in texts.items() if t.startswith("---")
              and scalar(t.split("---", 2)[1], "published") == "false"]
    for path in drafts:
        del texts[path]
    if drafts:
        print(f"Skipping {len(drafts)} unpublished documents.")
    covers = {scalar(t.split("---", 2)[1], "img") for t in texts.values() if t.startswith("---")}
    covers.discard(None)
    author = scalar(config, "author-img")
    if author:
        covers.add(author)
    sources = {}
    for path in sorted(source_dir.rglob("*")):
        if path.suffix.lower() not in PHOTO_EXTENSIONS or not path.is_file():
            continue
        key = path.relative_to(source_dir).as_posix()
        if key.startswith(("flags/", "favicon/")):
            continue
        signature = digest(path)
        previous = old.get(key, {})
        if previous.get("sha256") == signature:
            animated = previous.get("animated", False)
        else:
            with Image.open(path) as image:
                # Phone JPEGs may be MPO containers with an auxiliary frame,
                # which is not a displayed animation. Optimize the primary photo.
                animated = image.format in {"PNG", "GIF", "WEBP"} and getattr(image, "is_animated", False)
        sources[key] = {"sha256": signature, "animated": animated}
    for key in covers:
        if key not in sources and not (source_dir / key).is_file():
            raise ValueError(f"Missing cover/profile image: {key}")
    rewrites = {}
    for path, text in texts.items():
        rewritten, _ = prepare_document(path.relative_to(root), text, sources, root)
        if rewritten != text:
            rewrites[path] = rewritten
    # Validate configuration before generating files or migrating any source content.
    new_config = exclusion_config(config, [k for k, v in sources.items() if not v["animated"]])
    manifest = {}
    processed = skipped = 0
    original_bytes = output_bytes = 0
    def prepare_entry(item):
        key, info = item
        if info["animated"]:
            return key, info, 0, 0, 0, 0
        source = source_dir / key
        previous = old.get(key, {})
        variants = ["article"] + (["thumbnail"] if key in covers else [])
        reusable = (previous.get("sha256") == info["sha256"] and previous.get("settings") == SETTINGS
                    and all(v in previous and (root / unquote(previous[v]["path"]).lstrip("/")).is_file()
                            for v in variants))
        if reusable:
            entry = previous
        elif dry_run:
            return key, None, 1, 0, source.stat().st_size, 0
        else:
            entry = {**info, "settings": SETTINGS}
            for variant in variants:
                # Include the original extension: foo.png and foo.jpg cannot collide.
                target = root / "assets/optimized" / (key + "." + variant)
                output, size = render_image(source, target, thumbnail=variant == "thumbnail")
                entry[variant] = {"path": quote("/" + output.relative_to(root).as_posix(), safe="/"),
                                  "width": size[0], "height": size[1]}
        size = sum((root / unquote(entry[v]["path"]).lstrip("/")).stat().st_size for v in variants)
        return key, entry, int(not reusable), int(reusable), source.stat().st_size, size

    # Pillow releases the GIL during image processing. Bound concurrency to keep
    # memory use reasonable for camera-resolution originals on a laptop.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, entry, changed, unchanged, before, after in pool.map(prepare_entry, sources.items()):
            if entry is not None:
                manifest[key] = entry
            processed += changed
            skipped += unchanged
            original_bytes += before
            output_bytes += after
            if changed and processed % 100 == 0 and not dry_run:
                print(f"Processed {processed} photos…", flush=True)
    if not dry_run:
        write_changed(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        for path, text in rewrites.items():
            write_changed(path, text)
        write_changed(config_path, new_config)
    print(f"{'Would process' if dry_run else 'Processed'} {processed}; unchanged {skipped}; "
          f"{'would update' if dry_run else 'updated'} {len(rewrites)} documents.")
    if not dry_run:
        print(f"Originals: {original_bytes / 1e6:.1f} MB; web images including thumbnails: {output_bytes / 1e6:.1f} MB "
              f"({100 * (1 - output_bytes / original_bytes):.1f}% smaller)." if original_bytes else "No photos found.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing files")
    args = parser.parse_args()
    try:
        return run(ROOT, args.dry_run)
    except (ValueError, OSError, KeyError) as error:
        print(f"ERROR: {error}\nOriginal photos are untouched. Fix the error and rerun.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
