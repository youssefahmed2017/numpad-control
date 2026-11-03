"""The public half of the key that signs NumpadControl releases.

Every release is signed offline by the author (tools/sign-release). The updater installs
nothing the key hasn't signed, so a stolen GitHub account or a swapped download can't push
code to existing installs. Only the public key is here; the private key never goes in the
repository, CI or a cloud drive.

If the private key is ever lost or leaked, change this value in a release signed by the old
key (installs follow it), or reinstall by hand if the old key can't be trusted any more.
"""

PUBLIC_KEY = "YM2e0vgEBBJ7IBL7YBERWofJAwPBXEQnudhcUuqB060="  # base64 of the 32 raw bytes, made by "tools/sign-release keygen"
