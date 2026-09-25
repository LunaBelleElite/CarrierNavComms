# CarrierNavComms

**Your fleet carrier tells your Discord what it's doing, so you don't have to type it out.**

You schedule a jump, and a message lands in your channel with a live countdown
to departure. Someone drops tritium in the tank, sells cargo to the market, or
turns in a pile of exploration data at the carrier, and that shows up too. It
runs quietly inside EDMC while you play.

It needs no bot, no server and no account beyond a Discord webhook. Everything
it reports comes from your own Elite Dangerous journals.

## What lands in your channel

**When the carrier jumps**

- **Jump scheduled, cancelled and complete** each get their own message. The
  scheduled one carries a countdown Discord keeps ticking on its own, so
  nobody has to ask "when do we leave?".
- **Jump Complete names the star system the carrier left and the body it
  arrived at**, tracked from the carrier's own movements, not yours. If you
  weren't aboard, a fallback posts the arrival a minute and a half later,
  naming the systems but not the body, which Elite only tells whoever was there.

**When the carrier's market or tanks change**

- **Sell and Buy Orders** announce the item, price per ton and quantity, with
  a live "requested X ago" so a hauler knows how stale the order is.
- **Tritium deposits** from any commander and **trades at the carrier's
  market** each get a message, so the fuel gauge isn't a mystery.

**When someone cashes in exploration data at the carrier**

- **Universal Cartographics** turn-ins report the payout, systems and bonus.
  **First-discovery and first-mapped counts come from your own scans**, live:
  each body counts once, the tally resets when you sell, and it rebuilds from
  your recent journals when EDMC starts.
- **If Elite logs a sale with the payout zeroed, you see an estimate** marked
  with a tilde and a note, not a flat 0 CR. **Vista Genomics** turn-ins get
  their own message. **Sales are noticed even if you were already docked**
  when the game started.

**Around the messages**

- **Several carriers, each with its own webhooks,** in a scrolling list, with
  the carrier's picture and an Inara link on each message heading.
- **Jump and market-order messages only come from the owner's install.** Elite
  writes those events for everyone docked aboard, so otherwise every crew
  member running the plugin would post a duplicate. The owner's commander name
  comes from the Fetch ID button, or live from the game.
- **Every message but the not-aboard arrival note has a test button,** so you
  see what gets posted first.

## What it won't do

- **You have to be docked at the carrier for a sale to be reported.** Sales
  match a carrier by its numeric market ID, which keeps other stations out.
- **The payout shown is what the game logs,** which at a carrier can be below
  the base value because of the carrier's exploration tax, a game rule.
- **Fleet Carriers only,** so squadron carriers are ignored.
- **A real message that can't be delivered isn't reported anywhere you'll see
  it,** because messages go out in the background. The test button shows the
  error in red under the carrier card, so use it to check a webhook.

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
  release's, then read back to confirm nothing of yours went missing. If
  anything would, or `config.json` can't be read, the old `load.py` is put back
  and you're told. The old `load.py` also stays as `load.py.bak`. Templates
  you never edited get the new wording, ones you changed stay, new ones are
  added, and a `config.json` that isn't valid JSON is left exactly as it is.
- **Once you confirm, the install finishes even if you close the settings
  window.** On Windows it then closes EDMC and starts it again for you; a
  helper waits for EDMC to exit and starts nothing if it's still running after
  60 seconds, so no second copy appears. Elsewhere it installs and asks you to
  restart.

It needs nothing beyond GitHub and updates only from the
`LunaBelleElite/CarrierNavComms` releases. GitHub allows 60 anonymous requests
an hour, and you're told when they're used up. Copies from before the button
existed can't update themselves, so the first release with it goes in by hand.

## How it was built, and where to report trouble

CarrierNavComms was written with Claude Code, on Luna-Core (a starter kit for
running a project this way), alongside Astrid, an AI personality. Something
not working right? Open an issue on this project's page (forms for bugs and ideas),
attach your EDMC log if you can, and say whether you were docked at the carrier.
Questions or a chat? Find us on [Discord](https://discord.gg/64Gg9qdgsT).
