# Changelog

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
