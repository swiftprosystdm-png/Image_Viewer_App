"""
sps_crypto.py - Secure Decryption Engine for .sps Image Files.

Uses AES-256-GCM authenticated decryption to read .sps files directly in memory.
"""

import os
import json
import struct
import functools
import hashlib
from typing import Tuple, Dict, Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

MAGIC_HEADER = b"SPS1"
DEFAULT_PASSPHRASE = "SPS_SECURE_IMAGE_VIEWER_2026_KEY"
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
PBKDF2_ITERATIONS = 100_000


def get_passphrase_salt(passphrase: str) -> bytes:
    """Generate a consistent 16-byte salt for a passphrase to enable instant key caching across files."""
    return hashlib.sha256(b"SPS_KEY_SALT_V1:" + passphrase.encode("utf-8")).digest()[:SALT_SIZE]


@functools.lru_cache(maxsize=2048)
def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit cryptographic key from a passphrase and salt using PBKDF2 (Cached in RAM)."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def is_sps_file(file_path: str) -> bool:
    """Check if the specified file has the valid .sps magic header."""
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(len(MAGIC_HEADER))
            return header == MAGIC_HEADER
    except Exception:
        return False


def decrypt_sps_file(
    sps_path: str,
    passphrase: str = DEFAULT_PASSPHRASE
) -> Tuple[bytes, Dict[str, Any]]:
    """Decrypt a .sps file directly into RAM memory."""
    sps_abs_path = os.path.abspath(sps_path)
    if not os.path.isfile(sps_abs_path):
        raise FileNotFoundError(f".sps file not found: {sps_abs_path}")

    with open(sps_abs_path, "rb") as f:
        magic = f.read(len(MAGIC_HEADER))
        if magic != MAGIC_HEADER:
            raise ValueError(f"Invalid file format: Header does not match {MAGIC_HEADER.decode()}")
        
        salt = f.read(SALT_SIZE)
        nonce = f.read(NONCE_SIZE)
        tag = f.read(TAG_SIZE)
        ciphertext = f.read()

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    encrypted_blob = ciphertext + tag

    try:
        payload = aesgcm.decrypt(nonce, encrypted_blob, MAGIC_HEADER)
    except Exception as e:
        raise ValueError("Decryption failed. Invalid passphrase or corrupted file integrity.") from e

    meta_len = struct.unpack(">I", payload[:4])[0]
    meta_bytes = payload[4:4 + meta_len]
    image_bytes = payload[4 + meta_len:]

    metadata = json.loads(meta_bytes.decode("utf-8")) if meta_bytes else {}
    return image_bytes, metadata


def encrypt_sps_file(
    image_bytes: bytes,
    metadata: Dict[str, Any],
    sps_path: str,
    passphrase: str = DEFAULT_PASSPHRASE
) -> None:
    """Encrypt image bytes and metadata into an authenticated .sps file."""
    sps_abs_path = os.path.abspath(sps_path)
    salt = get_passphrase_salt(passphrase)
    nonce = os.urandom(NONCE_SIZE)
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    meta_json = json.dumps(metadata).encode("utf-8") if metadata else b""
    payload = struct.pack(">I", len(meta_json)) + meta_json + image_bytes
    encrypted_blob = aesgcm.encrypt(nonce, payload, MAGIC_HEADER)

    # In cryptography AESGCM, the last TAG_SIZE bytes of the encrypted result are the auth tag
    ciphertext = encrypted_blob[:-TAG_SIZE]
    tag = encrypted_blob[-TAG_SIZE:]

    with open(sps_abs_path, "wb") as f:
        f.write(MAGIC_HEADER)
        f.write(salt)
        f.write(nonce)
        f.write(tag)
        f.write(ciphertext)

