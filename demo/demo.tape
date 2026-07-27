# vhs script for the README demo GIF. Re-record with:
#
#     vhs demo/demo.tape          # from the repository root
#
# The chats are fabricated (see demo/fake_run.py); the output is the real
# tool's. Re-record whenever the CLI's output changes, so the GIF can't drift
# into advertising behaviour the tool no longer has.

Output docs/demo.gif

Require vhs

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 640
Set Padding 18
Set Framerate 24
Set TypingSpeed 45ms

# Put the recording shim on PATH and get a clean one-character prompt.
Hide
Type `export PATH="$PWD/demo/bin:$PATH" PS1="$ "` Enter
Type "clear" Enter
Show

# --- The dry run: the whole pitch. Lists matches, touches nothing. ----------
Type `tg-bulk-leave --keyword acme --keyword airdrop --protected "Acme Alumni"`
Sleep 600ms
Enter
Sleep 4s

Hide
Type "clear" Enter
Show
Sleep 500ms

# --- The real run: explicit opt-in, capped, and gated on a typed word. ------
Type "tg-bulk-leave -k acme -k airdrop -p 'Acme Alumni' --execute --limit 3"
Sleep 600ms
Enter
Sleep 3s

# The confirmation gate. Only the exact string LEAVE proceeds.
Type "LEAVE"
Sleep 800ms
Enter

# Leaves are paced 2.5-5.0s apart on purpose; this is real time, not an edit.
# Sized for the worst case (two 5s gaps) plus a beat to read the summary.
Sleep 12s
