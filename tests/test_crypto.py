import unittest
import os
import base64
from catlogs import crypto

class TestCrypto(unittest.TestCase):

    def test_encrypt_decrypt_data(self):
        original = b"This is a top secret message!"
        encrypted = crypto.encrypt_data(original)
        
        self.assertNotEqual(original, encrypted)
        self.assertTrue(encrypted.startswith(b"v2:"))
        
        decrypted = crypto.decrypt_data(encrypted)
        self.assertEqual(original, decrypted)

    def test_encrypt_decrypt_str(self):
        original = "Hello World! Here is a string with some special chars: !@#$%^&*()"
        encrypted = crypto.encrypt_str(original)
        
        self.assertNotEqual(original, encrypted)
        self.assertIsInstance(encrypted, str)
        
        decrypted = crypto.decrypt_str(encrypted)
        self.assertEqual(original, decrypted)

    def test_decrypt_empty(self):
        self.assertEqual(crypto.decrypt_data(b""), b"")
        self.assertEqual(crypto.encrypt_data(b""), b"")
        
        self.assertEqual(crypto.decrypt_str(""), "")

    def test_legacy_decryption(self):
        original = b"Legacy string"
        # Simulate legacy XOR encryption using SEC_KEY
        key = crypto.SEC_KEY
        legacy_enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(original))
        
        decrypted = crypto.decrypt_data(legacy_enc)
        self.assertEqual(original, decrypted)

    def test_encrypted_filename(self):
        name1 = crypto.get_encrypted_filename("test.log")
        name2 = crypto.get_encrypted_filename("test.log")
        name3 = crypto.get_encrypted_filename("other.log")
        
        self.assertEqual(name1, name2)
        self.assertNotEqual(name1, name3)
        self.assertTrue(name1.endswith(".dat"))
        self.assertEqual(len(name1), 16 + 4) # 16 chars + ".dat"

if __name__ == "__main__":
    unittest.main()
