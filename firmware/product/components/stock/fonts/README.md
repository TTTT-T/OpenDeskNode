# Stock component font subsets

Generated once with `lv_font_conv` 1.5.3 (npx-pinned) from the Source Han Sans
SC Normal OTF that ships inside the LVGL managed component. Source Han Sans is
distributed under the SIL Open Font License 1.1 (see
`managed_components/lvgl__lvgl/scripts/built_in_font/font_license/SourceHanSansSC/LICENSE.txt`),
which permits redistribution of subsets. No macOS system fonts and no network
glyph fetching at build or runtime.

Provenance (input file, byte-identical to the LVGL managed component copy):

    firmware/product/managed_components/lvgl__lvgl/scripts/built_in_font/SourceHanSansSC-Normal.otf

Regenerate from the repository root (requires node/npx):

    npx --yes lv_font_conv@1.5.3 --no-compress --bpp 1 --size 24 \
      --font firmware/product/managed_components/lvgl__lvgl/scripts/built_in_font/SourceHanSansSC-Normal.otf \
      -r 0x20-0x7E,0x4E00-0x9FEF --symbols "▲▼" \
      --format lvgl --lv-font-name stock_font_cjk_24 \
      -o firmware/product/components/stock/fonts/stock_font_cjk_24.c

    npx --yes lv_font_conv@1.5.3 --no-compress --bpp 1 --size 48 \
      --font firmware/product/managed_components/lvgl__lvgl/scripts/built_in_font/SourceHanSansSC-Normal.otf \
      -r 0x2B,0x2D,0x2E,0x25,0x30-0x39 \
      --format lvgl --lv-font-name stock_font_num_48 \
      -o firmware/product/components/stock/fonts/stock_font_num_48.c

Notes:

- 1 bpp, no compression, no kerning store: crisp thresholded rendering on the
  monochrome ST7305 and small flash cost.
- `stock_font_cjk_24.c`: ASCII 0x20-0x7E, the complete CJK Unified Ideographs
  range U+4E00-0x9FEF available in the pinned Source Han Sans SC font,
  U+25B2 ▲, and U+25BC ▼. This supports Web-managed
  A-share short names without maintaining a firmware name whitelist; common
  `ST`, `*ST`, `N`, `C`, `-U`, and `-W` markers are covered by ASCII.
- `stock_font_num_48.c`: digits, `+ - . %` for the large price line.
- The Phase 1E verifier asserts every code point in the basic CJK block plus
  both arrows. Characters outside that declared range remain unsupported.
