"""
Snowflake key-pair auth setup, per developer.

  uv run python scripts/snowflake_keypair_setup.py

Generates an RSA keypair locally, prints the SQL to register the public key
on your Snowflake user, and prints the env vars to add to .env. The private
key never leaves your machine.

Each teammate runs this once. The Snowflake account owner runs the printed
ALTER USER SQL once per teammate to register their public key.

Default key location: ~/.snowflake/<user>_rsa_key.p8 (gitignored).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Snowflake RSA keypair for key-pair auth")
    parser.add_argument("--user", help="Snowflake username (used in filename + ALTER USER stmt)",
                        default=os.environ.get("SNOWFLAKE_USER"))
    parser.add_argument("--out-dir", default=str(Path.home() / ".snowflake"),
                        help="Directory to write keys to (default: ~/.snowflake)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing key files")
    args = parser.parse_args()

    if not args.user:
        print(f"{RED}error:{RESET} no --user given and SNOWFLAKE_USER is unset")
        print("Usage: uv run python scripts/snowflake_keypair_setup.py --user YOUR_NAME")
        return 1

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print(f"{RED}error:{RESET} cryptography package missing — run `make install`")
        return 1

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o700)

    priv_path = out_dir / f"{args.user}_rsa_key.p8"
    pub_path = out_dir / f"{args.user}_rsa_key.pub"

    if (priv_path.exists() or pub_path.exists()) and not args.force:
        print(f"{YELLOW}!{RESET} key files already exist at {out_dir}")
        print(f"  {priv_path}")
        print(f"  {pub_path}")
        print("  Re-run with --force to overwrite, or use the existing key.")
        return 1

    # Generate RSA 2048 keypair
    print(f"Generating RSA 2048 keypair for user {BOLD}{args.user}{RESET}…")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Write private key as unencrypted PKCS#8 (.p8)
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    priv_path.write_bytes(priv_bytes)
    priv_path.chmod(0o600)
    print(f"  {GREEN}✓{RESET} private key: {priv_path} (chmod 600)")

    # Write public key in DER-then-base64 inside PEM headers
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_path.write_bytes(pub_bytes)
    pub_path.chmod(0o644)
    print(f"  {GREEN}✓{RESET} public key: {pub_path}")

    # Snowflake's ALTER USER ... SET RSA_PUBLIC_KEY wants the base64 body
    # between the BEGIN/END PUBLIC KEY headers, no newlines.
    pub_text = pub_bytes.decode()
    pub_body = "".join(
        line for line in pub_text.splitlines() if not line.startswith("---")
    )

    print()
    print(f"{BOLD}NEXT STEPS{RESET}")
    print()
    print(f"{BOLD}1.{RESET} Send the public key to your Snowflake admin (whoever owns the account).")
    print("   They run this in a Snowflake worksheet:")
    print()
    print(f"   {GREEN}ALTER USER {args.user} SET RSA_PUBLIC_KEY='{pub_body}';{RESET}")
    print()
    print(f"{BOLD}2.{RESET} Add these to your local {BOLD}.env{RESET} (gitignored):")
    print()
    print("   SNOWFLAKE_ACCOUNT=<your-account-locator>")
    print(f"   SNOWFLAKE_USER={args.user}")
    print(f"   SNOWFLAKE_PRIVATE_KEY_PATH={priv_path}")
    print("   # SNOWFLAKE_PASSWORD=  ← remove or leave blank (key-pair takes priority)")
    print("   SNOWFLAKE_WAREHOUSE=DISASTER_WH")
    print("   SNOWFLAKE_DATABASE=DISASTER_DB")
    print("   SNOWFLAKE_SCHEMA=CLEAN")
    print()
    print(f"{BOLD}3.{RESET} Verify the connection:")
    print()
    print(f"   {GREEN}make snowflake-smoke{RESET}")
    print()
    print(f"   You should see: {GREEN}snowflake: using key-pair auth{RESET}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
