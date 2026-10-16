# W3 browser integration: host release, board execution pending

2026-10-14. The downloaded W2 board run has independently passed 80 frames and 13,303,808 exact output words, including original observer pages and actual parameter/cycle readback. See `../w2_quality_2017_4/board_execution_2026-10-14/verification.json`. W3 reuses that exact bit/HWH; no hardware rebuild or HDMI path was introduced.

## Changes and derivation

- `pynq_w3` and `ui_w3` are isolated derivatives of the verified W1 service/UI. `derivation.json` records original/new hashes; `w1_to_w3.diff` records the controlled source changes. The released W1 33-artifact inventory and W2 10-artifact inventory were checked unchanged.
- Requests carry real A/C2, integer threshold 1..255, size and processing mode. The single worker writes the W2 control ABI and verifies completed RQ21 control, tag, sequence, words and cycles. Actual FCLK0 must read 100 MHz. The driver/observer/DDR/DMA paths are preserved.
- Returned masks, enhancement, overlays and metrics derive from completed DMA output. CPU unpacking, read-only snapshots, area/GT evaluation and PNG generation remain separate from medical PL computation. No host reference, golden output or synthetic hardware implementation is shipped in the application.
- Changed selections immediately mark old results stale, remove old metrics and disable current export. A late response cannot restore old metrics. The continuous loop locks its configuration and excludes a hidden interval from displayed FPS. Display-only opacity remains labelled separately.
- PL core cycles include streaming wait. The DMA transaction encloses overlapping PL execution; no subtraction invents pure transport time. W3 inference is configuration through snapshot and includes buffer allocation, matching W1; W2's older diagnostic boundary excluded allocation. Observer readback is separately recorded after snapshot. Full performance and pure DMA transport remain pending.

## Executed host checks

The final run in `w3_host_tests_final.log` passed **31 distinct tests, zero skips**. This covers real control-word handling, tag wrap, observer failures, native buffer ownership/failure retention, clock/driver checks, API queue/nonces/exports, actual output decoding/metrics, stale-selection handling, loop identity/visibility, and runtime/reference separation. The unchanged observer decoder also replayed all 80 original W2 board records.

All logs remain byte-for-byte as produced. The first 25-test run had one failure because the synthetic bypass transfer completed faster than the fixture's synthetic PL cycle duration. The host fixture was corrected to include its declared duration; the production enclosing-DMA-window check was not weakened. The next 25-test run passed, the five contract tests passed, and the final combined run added the stable-configuration loop test for 31 distinct tests.

Using the actual browser UI at localhost with a prominent **HOST TEST** banner, the first session exercised A/C2 switching, threshold changes, stale results, four panels, exports and 20-frame foreground looping. After the final UI changes, the second session exercised C2/T40, immediate threshold-input invalidation, C2/T28 and a 20-frame foreground loop: **21 tasks**. Its downloaded ZIP was independently checked for all output words, PNG pixels, AH/VK scores, readback/timing fields and exact FPS arithmetic. It matched the final release manifest. These synthetic values are **not new board performance or medical-quality evidence**. The labelled ZIPs and visually inspected full-page screenshot are preserved locally under `build/browser_w3_ui_qa`; hashes are in `host_evidence_files.json`. The temporary browser tab and preview service were stopped after verification.

## Delivered package

`build/deploy/browser_w3_upload_r1` contains exactly two upload files:

| File | Bytes | SHA-256 |
|---|---:|---|
| browser_w3_c2_r1.zip | 1,736,369 | fa0b51356e09e7912b88fd7e60662806b8f5bfa12028c700d517164a8dc111ce |
| browser_w3_start.ipynb | 7,871 | f12883a6cdb4bd3edbe98c5dbbf895676bed5517f7d8a143f735d87bc0aacfee |

The ZIP contains 26 artifacts plus its manifest. All source/package bytes, ZIP CRC/inventory, Python 3.10 syntax and six unexecuted startup cells were checked. The startup notebook pins the ZIP hash. `release_validation.json` records the complete evidence, including preserved original releases and host UI totals.

Next: follow `docs/browser_w3_board_steps.md` in a fresh `retina_browser_w3_r1`, execute eight manual configurations and 20 foreground C2 frames. Download `browser_w3_session_bundle.zip` and the executed `browser_w3_start.ipynb`; use `scripts/verify_browser_w3_archive.py` to recheck the complete board evidence. The verifier rejects HOST previews as board evidence. W3 board status remains **NOT_RUN**, new browser FPS remains **unmeasured**, and formal W4+Q3 quality/performance and W5 stability are pending. The single-image W2 bright-band improvement does not establish full-dataset quality.
