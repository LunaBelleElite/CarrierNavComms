# Changelog

## Versioning scheme

This project uses a 4-number version format: `ver-A.B.C.D`. The `ver-` prefix is always present.

- **A (1st number):** a complete redesign/rewrite of the whole program or layout.
- **B (2nd number):** changes to core features, short of a full redesign.
- **C (3rd number):** large bug fixes.
- **D (4th number):** very small bug fixes. A doc/spec-only addition (no feature, no bugfix) counts as a 4th-number change too, same treatment as a minor bugfix.

Any number can climb arbitrarily high. When a higher-order number increments, every number to its right resets to 0.

This repository's first release is `ver-1.0.0.0`, and its releases are tagged with the version exactly as written above.

(This section is not edited when entries below are added, only when the scheme itself changes.)

## ver-1.1.0.0 - 2026-09-25

- Added a **Check for updates** button at the bottom of the plugin's settings tab. It looks up the
  latest release, asks before installing, does one update at a time, and never installs an older version.
- The download is checked before anything is touched, and any problem shows as a plain message.
- Your carriers, webhooks and settings are kept and backed up. If anything of yours would go missing,
  or `config.json` can't be read, the old plugin file is put back. Message templates you never edited
  get the new wording; ones you changed stay.
- On Windows it closes EDMC and starts it again for you; elsewhere it installs and asks you to restart.
- Added a README.
- Installs older than 1.1.0.0 have no button, so the first update is by hand.

## ver-1.0.0.0 - 2026-09-24

- First release of this repository. It ships exactly two files, `load.py` and `config.json`
  (no carriers or webhooks in it).
- Fixed: a data sale at your carrier could go unposted if EDMC started while you were docked.
  It's reported now.
- Fixed: when Elite logs a Universal Cartographics sale with the payout zeroed out, the message
  shows an estimate marked with `~` and a short note, instead of announcing 0 CR. A payout that
  really is zero is still reported as zero.
