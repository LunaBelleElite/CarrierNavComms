# Changelog

## ver-1.1.0.3 - 2026-09-25

- The **Check for updates** restart is safer and explains itself. On a couple of occasions EDMC closed after an update and didn't reopen, so the restart now:
  - keeps a small log, `restart-helper.log`, in the plugin's folder, of what it did;
  - checks that EDMC actually came back, and tries once more if it didn't;
  - won't try to restart while EDMC is already closing.
- If EDMC ever fails to come back, that log shows what happened, and it's shown in EDMC's own log at the next start.
- Installs on 1.1.0.0 or newer will offer this through the **Check for updates** button.

## ver-1.1.0.2 - 2026-09-25

- Added issue forms for bug reports and ideas on the repository's Issues page, so it's clearer what to include.
- Added a link to the community Discord (https://discord.gg/64Gg9qdgsT) to the README.
- The repository's About link now points to the Discord.
- Installs on 1.1.0.0 will offer this through the **Check for updates** button.

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
