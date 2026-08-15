# Stock component font subsets (Phase 1C)

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
      -r 0x20-0x7E --symbols "▲▼中国平安贵州茅台宁德时代比亚迪涨跌停牌" \
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
- `stock_font_cjk_24.c`: ASCII 0x20-0x7E, U+25B2 ▲, U+25BC ▼, and exactly the
  CJK glyphs needed by the four deterministic mock names (贵州茅台, 宁德时代,
  比亚迪, 中国平安) plus 涨停/跌停/停牌 status text.
- `stock_font_num_48.c`: digits, `+ - . %` for the large price line.
- The mock name/status strings are constrained by
  `scripts/verify-phase-1c.sh` to glyphs this font actually contains, so a
  runtime change of mock text without regenerating the font fails statically
  instead of rendering tofu.
