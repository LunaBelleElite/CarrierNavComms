# CarrierNavComms

**Your fleet carrier tells your Discord what it's doing, so you don't have to type it out.**

You schedule a jump, and a message lands in your channel with a live countdown
to departure. Someone drops tritium in the tank, sells cargo to the market, or
turns in a pile of exploration data at the carrier, and that shows up too. It
runs quietly inside EDMC while you play.

It needs no bot, no server and no account beyond a Discord webhook. Everything
it reports comes from your own Elite Dangerous journals.

## What lands in your channel

- **Jump scheduled, cancelled and complete** each get their own message. The
  scheduled one carries a countdown Discord keeps ticking on its own, so
  nobody has to ask "when do we leave?".
- **Jump Complete names the star system the carrier left and the body it
  arrived at**, tracked from the carrier's own movements, not yours. If you
  weren't aboard, a fallback posts the arrival a minute and a half later,
  naming the systems but not the body, which Elite only tells whoever was there.
- **Sell and Buy Orders** give the item, price per ton and quantity, with a
  live "requested X ago" so a hauler knows how stale the order is.
- **Tritium deposits** from any commander and **trades at the carrier's
  market** each get a message, so the fuel gauge isn't a mystery.
- **Universal Cartographics** turn-ins report the payout, systems and bonus,
  with **first-discovery and first-mapped counts from your own scans**: each
  body counts once, the tally resets when you sell, and it rebuilds from your
  journals when EDMC starts. If Elite logs the payout zeroed, **you see an
  estimate** marked with a tilde and a note, not a flat 0 CR.
- **Vista Genomics** turn-ins get their own message. Sales are noticed even if
  you were already docked when the game started.
- **Several carriers, each with its own webhooks**, with the carrier's picture
  and an Inara link on each message heading.
- **Jump and market-order messages only come from the owner's install**, so
  crew members running the plugin aboard don't post duplicates. The owner's
  name comes from the Fetch ID button, or live from the game.

## What it won't do

- **You have to be docked at the carrier for a sale to be reported.** Sales
  match a carrier by its numeric market ID, which keeps other stations out.
- **The payout shown is what the game logs,** which at a carrier can be below
  the base value because of the carrier's exploration tax, a game rule.
- **Fleet Carriers only,** so squadron carriers are ignored.
- **A failed message won't pop up a warning while you play,** because messages
  go out in the background. It's written down instead, as below, and a test
  button shows its error in red under the carrier card.

## What you need

- **EDMC** (Elite Dangerous Market Connector) and Elite Dangerous.
- **A Discord webhook for each channel,** made in the channel's settings on
  Discord under Integrations. It posts only where you point it.

## Getting started

1. Extract the download into EDMC's plugins folder (EDMC's settings has a
   button that opens it, under Plugins), then restart EDMC.
2. In EDMC's settings, open the **CarrierNavComms** tab, click
   **+ Add Fleet Carrier**, type its callsign in **Callsign (ID)** and click
   **Fetch ID**. It searches your recent journals for the carrier's numeric ID;
   if it finds nothing, dock at the carrier once and try again.
3. Fill in **Name** and an **Inara URL** for the carrier's picture, paste
   webhooks under **Discord Webhook Channels** with **+ Add New Webhook**, and
   press Apply or OK to save.
4. Press a test button on the carrier card, such as **Tritium Deposited**
   (the owner-only tests need the game running). A test message appears in
   your Discord channel, with the carrier's picture if you gave an Inara link.

The settings box adapts to the room it has: on a short screen it goes compact
and tucks each carrier's test buttons behind a **Send test messages** toggle, and it moves itself fully into view when it opens.

## Each carrier can drop the picture

Untick **Use Inara image** on a carrier card and its messages skip the Inara
lookup and carry no picture, so more fit on screen in a busy channel; the
heading still links to Inara. It's on by default, so your carriers keep their
picture, and it's saved per carrier through updates.

## A failed post tells you why

If Discord turns a message down or can't be reached, the reason is kept (the
HTTP status and Discord's own words, a rate-limit wait, a timeout, or "could
not connect"), naming the channel by its number in your list:

- **The settings tab's Last post line** reads OK with the time, FAILED with
  the reason, or none yet (as it does after every restart). It refreshes when
  you open the tab or press a test button.
- **`post-failures.log` in the plugin folder** keeps the history, moving to
  `post-failures.log.old` once it reaches 32 KB.
- **EDMC's log** gets a `post failed` line at once, and the last three again
  when EDMC starts.

Your webhook address never appears in any of them. Nothing is retried, so fix
the webhook and press a test button to check it.

## Updates itself when you tell it to

At the bottom of the **CarrierNavComms** settings tab, **Check for updates**
looks up the latest release. Nothing goes online until you click.

- **It asks before it installs anything, one update at a time, and never
  installs an older version.** The confirmation warns that unsaved settings
  changes and a pending not-aboard arrival note are lost, so press Apply first.
- **It checks the download before touching your files:** size and SHA-256
  against what GitHub publishes, exactly two files in the zip, a `load.py` that
  compiles and names its own version, and no carriers in the release's settings.
  A failure shows a plain message and changes nothing.
- **Your carriers and webhooks are backed up and checked.** `config.json` is
  copied to `config.json.bak-<stamp>` (newest three kept), rebuilt around the
  release's and read back; if anything of yours would go missing, or it can't
  be read, the old `load.py` (also kept as `load.py.bak`) goes back and you're
  told. Templates you never edited get the new wording, yours stay, new ones
  are added, and a `config.json` that isn't valid JSON is left as it is.
- **Once you confirm, the install finishes even if you close the settings
  window.** On Windows it closes EDMC and a helper opens it again. The helper
  starts nothing if EDMC is still running after 60 seconds, so no second copy
  appears; it checks EDMC came back, tries once more if not, and writes what
  it did to `restart-helper.log` in the plugin folder. Elsewhere it installs
  and asks you to restart.

It needs nothing beyond GitHub and updates only from the
`LunaBelleElite/CarrierNavComms` releases. GitHub allows 60 anonymous requests
an hour, and you're told when they're used up. A copy older than the button
has to be updated by hand, once.

## How it was built, and where to report trouble

CarrierNavComms was written with Claude Code, on Luna-Core (a starter kit for
running a project this way), alongside Astrid, an AI personality. Something
not working right? Open an issue on this project's page (there are forms for
bugs and ideas), attach your EDMC log and `post-failures.log` if you have them,
and say whether you were docked at the carrier. Questions or a chat? Find us
on [Discord](https://discord.gg/64Gg9qdgsT).
