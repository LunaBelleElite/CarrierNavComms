# Changelog

## ver-1.2.1.0 - 2026-09-26

- The settings box now opens fully in view. If EDMC opens it partly off the bottom or the side of the screen, it is moved back on screen, title bar and OK/Cancel row included, and kept clear of the taskbar. It is never resized, and a box you drag yourself is left alone.
- It has been checked on a simulated small screen and on one real desktop, not inside EDMC on a small monitor.
- Installs on 1.1.0.0 or newer will offer this through the **Check for updates** button.

## ver-1.2.0.0 - 2026-09-26

- When a message doesn't reach Discord, you can now see why. The reason (Discord's own words, a rate-limit wait, a timeout, or "could not connect") is recorded by channel number, never your webhook address, in three places: a **Last post** line in the plugin's settings tab, `post-failures.log` in the plugin's folder, and EDMC's own log.
- Nothing is retried automatically: a failed message stays failed, so fix the webhook and press a test button to check it.
- Each carrier has a new **Use Inara image** switch. Turn it off and that carrier's messages skip the Inara lookup and carry no picture, so more of them fit on screen in a busy channel. The Inara link in the heading stays. It's on by default, so carriers you already have keep their picture.
- The settings box fits smaller screens. When space is short it switches to a compact layout that shows at least one and a half carriers, with each carrier's test buttons behind a **Send test messages** toggle. It has been checked on simulated screen sizes only, not on a real small monitor.
- Installs on 1.1.0.0 or newer will offer this through the **Check for updates** button.

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
