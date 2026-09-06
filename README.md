# All Passport Stamps

A static Jekyll travel blog hosted on GitHub Pages.

## Set up image optimization once

From the repository directory, with Python 3.11 or newer installed:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r scripts/requirements.txt
```

Dependency installation needs internet. After that, image optimization works entirely offline, including on planes. Activate the environment with `source .venv/bin/activate` when opening a new terminal. The `.venv` directory is ignored by Git.

## Write a post and prepare its photos

1. Copy full-resolution photos into `assets/img/`, for example `assets/img/italy/hotel_1.jpeg`.
2. Write the post using the **original** image paths, just as before:

   ```markdown
   ![View from the hotel]({{site.baseurl}}/assets/img/italy/hotel_1.jpeg){:width="50%"}
   ```

   The optional percentage width preserves the existing side-by-side layout. Cover front matter also stays unchanged: `img: italy/hotel_1.jpeg`.

3. Run the optimizer from the repository:

   ```sh
   python3 scripts/optimize_images.py
   ```

4. Preview with the existing Jekyll setup:

   ```sh
   bundle exec jekyll serve
   ```

   Open `http://localhost:4000`. Jekyll dependencies must also have been installed before going offline.

5. Review and commit the original photos, generated `assets/optimized/` files, `_data/images.json`, updated posts, and `_config.yml`. Push when internet is available.

**Run the optimizer after adding or changing photos and before publishing.** GitHub Pages does not run Python automatically. The command does not commit, push, or publish anything.

To inspect what would change without writing files:

```sh
python3 scripts/optimize_images.py --dry-run
```

## What the command changes

Originals in `assets/img/` are never overwritten. Article copies are limited to 1,600 pixels on the longest edge and saved as progressive JPEGs at quality 82. Homepage covers also get thumbnails up to 800 pixels wide. Smaller photos are not enlarged. Transparent PNGs keep transparency; SVG flags, favicons, and animations are left alone.

The script automatically converts supported Markdown photo references into a Jekyll include. For example, a photo near the beginning of an article becomes:

```liquid
{% include image.html src="italy/hotel_1.jpeg" alt="View from the hotel" width="50%" loading="eager" %}
```

The include retains the **original identifier**, but renders the optimized URL and image dimensions. Later photos default to lazy loading; the first two article photos, article cover, profile image, and first two homepage thumbnails load eagerly. Captions and percentage widths remain in place. You can continue adding new photos with ordinary Markdown and let the next run convert them.

Generated files use names such as `assets/optimized/italy/hotel_1.jpeg.article.jpg`; retaining the source extension prevents a JPEG and PNG with the same stem from colliding. `_data/images.json` records output paths, dimensions, source hashes, and settings. Commit both the metadata and generated images.

The script maintains a marked section of the Jekyll `exclude` list in `_config.yml`. This keeps originals in Git but excludes them from the published site. Flags, favicons, and animations remain available. Do not edit the generated exclusion block by hand.

## Updating photos and troubleshooting

- Replace an original at the same path and rerun the command to refresh its web copies. Unchanged photos are skipped; repeating the command does not repeatedly compress a JPEG.
- Settings live in `SETTINGS` near the top of `scripts/optimize_images.py`. Changing them causes regeneration from originals on the next run.
- Missing files, unreadable photos, and unsupported image markup produce an error with a nonzero exit status. Fix the named issue and rerun before publishing. Comments and code examples are not migrated.
- Automatic conversion supports inline Markdown images with optional percentage-width attributes. Other custom HTML or image attributes require manual adaptation to the include; the script reports these instead of silently breaking references.
- Documents marked `published: false` are skipped. Rerun the command when making a draft publishable.
- A processing interruption may leave some generated files. Originals remain untouched; rerun the command to finish. Stale generated files are not automatically deleted.
- Keeping originals in Git means the repository stays large even though the published pages become much lighter. This script does not rewrite Git history.

Run the optimizer's regression tests with:

```sh
python3 -m unittest discover -s tests -v
```
