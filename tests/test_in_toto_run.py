#!/usr/bin/env python

"""
<Program Name>
  test_in_toto_run.py

<Author>
  Lukas Puehringer <lukas.puehringer@nyu.edu>

<Started>
  Nov 28, 2016

<Copyright>
  See LICENSE for licensing information.

<Purpose>
  Test in_toto_run command line tool.

"""

import os
import sys
import unittest
import glob

# Use external backport 'mock' on versions under 3.3
if sys.version_info >= (3, 3):
  import unittest.mock as mock # pylint: disable=no-name-in-module,import-error
else:
  import mock # pylint: disable=import-error

from in_toto.util import (generate_and_write_rsa_keypair,
    generate_and_write_ed25519_keypair, import_private_key_from_file,
    KEY_TYPE_RSA, KEY_TYPE_ED25519)

from in_toto.models.metadata import Metablock
from in_toto.in_toto_run import main as in_toto_run_main
from in_toto.models.link import FILENAME_FORMAT

from tests.common import CliTestCase, TmpDirMixin, GPGKeysMixin


class TestInTotoRunTool(CliTestCase, TmpDirMixin, GPGKeysMixin):
  """Test in_toto_run's main() - requires sys.argv patching; and
  in_toto_run- calls runlib and error logs/exits on Exception. """
  cli_main_func = staticmethod(in_toto_run_main)

  @classmethod
  def setUpClass(self):
    """Create and change into temporary directory,
    generate key pair, dummy artifact and base arguments. """
    self.set_up_test_dir()
    self.set_up_gpg_keys()

    self.rsa_key_path = "test_key_rsa"
    generate_and_write_rsa_keypair(self.rsa_key_path)
    self.rsa_key = import_private_key_from_file(self.rsa_key_path,
        KEY_TYPE_RSA)

    self.ed25519_key_path = "test_key_ed25519"
    generate_and_write_ed25519_keypair(self.ed25519_key_path)
    self.ed25519_key = import_private_key_from_file(self.ed25519_key_path,
        KEY_TYPE_ED25519)

    self.test_step = "test_step"
    self.test_link_rsa = FILENAME_FORMAT.format(step_name=self.test_step, keyid=self.rsa_key["keyid"])
    self.test_link_ed25519 = FILENAME_FORMAT.format(step_name=self.test_step, keyid=self.ed25519_key["keyid"])
    self.test_artifact = "test_artifact"
    open(self.test_artifact, "w").close()

  @classmethod
  def tearDownClass(self):
    self.tear_down_test_dir()

  def tearDown(self):
    for link in glob.glob("*.link"):
      os.remove(link)

  def test_main_required_args(self):
    """Test CLI command with required arguments. """

    args = ["--step-name", self.test_step, "--key", self.rsa_key_path, "--",
        "python", "--version"]

    # Give wrong password whenever prompted.
    with mock.patch('in_toto.util.prompt_password', return_value='x'):
      self.assert_cli_sys_exit(args, 0)

    self.assertTrue(os.path.exists(self.test_link_rsa))


  def test_main_optional_args(self):
    """Test CLI command with optional arguments. """

    named_args = ["--step-name", self.test_step, "--key",
        self.rsa_key_path, "--materials", self.test_artifact, "--products",
        self.test_artifact, "--record-streams"]
    positional_args = ["--", "python", "--version"]

    # Give wrong password whenever prompted.
    with mock.patch('in_toto.util.prompt_password', return_value='x'):

      # Test and assert recorded artifacts
      args1 = named_args + positional_args
      self.assert_cli_sys_exit(args1, 0)
      link_metadata = Metablock.load(self.test_link_rsa)
      self.assertTrue(self.test_artifact in
          list(link_metadata.signed.materials.keys()))
      self.assertTrue(self.test_artifact in
          list(link_metadata.signed.products.keys()))

      # Test and assert exlcuded artifacts
      args2 = named_args + ["--exclude", "*test*"] + positional_args
      self.assert_cli_sys_exit(args2, 0)
      link_metadata = Metablock.load(self.test_link_rsa)
      self.assertFalse(link_metadata.signed.materials)
      self.assertFalse(link_metadata.signed.products)

      # Test with base path
      args3 = named_args + ["--base-path", self.test_dir] + positional_args
      self.assert_cli_sys_exit(args3, 0)
      link_metadata = Metablock.load(self.test_link_rsa)
      self.assertListEqual(list(link_metadata.signed.materials.keys()),
          [self.test_artifact])
      self.assertListEqual(list(link_metadata.signed.products.keys()),
          [self.test_artifact])

      # Test with bogus base path
      args4 = named_args + ["--base-path", "bogus/path"] + positional_args
      self.assert_cli_sys_exit(args4, 1)

      # Test with lstrip path
      strip_prefix = self.test_artifact[:-1]
      args5 = named_args + ["--lstrip-paths", strip_prefix] + positional_args
      self.assert_cli_sys_exit(args5, 0)
      link_metadata = Metablock.load(self.test_link_rsa)
      self.assertListEqual(list(link_metadata.signed.materials.keys()),
          [self.test_artifact[len(strip_prefix):]])
      self.assertListEqual(list(link_metadata.signed.products.keys()),
          [self.test_artifact[len(strip_prefix):]])


  def test_main_with_unencrypted_ed25519_key(self):
    """Test CLI command with ed25519 key. """
    args = ["-n", self.test_step,
        "--key", self.ed25519_key_path,
        "--key-type", "ed25519", "--", "ls"]

    self.assert_cli_sys_exit(args, 0)
    self.assertTrue(os.path.exists(self.test_link_ed25519))


  def test_main_with_encrypted_ed25519_key(self):
    """Test CLI command with encrypted ed25519 key. """
    key_path = "test_key_ed25519_enc"
    password = "123456"
    generate_and_write_ed25519_keypair(key_path, password)
    args = ["-n", self.test_step,
        "--key", key_path,
        "--key-type", "ed25519", "--", "ls"]

    with mock.patch('in_toto.util.prompt_password', return_value=password):
      key = import_private_key_from_file(key_path, KEY_TYPE_ED25519)
      linkpath = FILENAME_FORMAT.format(step_name=self.test_step, keyid=key["keyid"])

      self.assert_cli_sys_exit(args, 0)
      self.assertTrue(os.path.exists(linkpath))


  def test_main_with_specified_gpg_key(self):
    """Test CLI command with specified gpg key. """
    args = ["-n", self.test_step,
            "--gpg", self.gpg_key_85DA58,
            "--gpg-home", self.gnupg_home, "--", "python", "--version"]

    self.assert_cli_sys_exit(args, 0)
    link_filename = FILENAME_FORMAT.format(step_name=self.test_step,
        keyid=self.gpg_key_85DA58)

    self.assertTrue(os.path.exists(link_filename))


  def test_main_with_default_gpg_key(self):
    """Test CLI command with default gpg key. """
    args = ["-n", self.test_step,
            "--gpg", "--gpg-home", self.gnupg_home, "--", "python", "--version"]

    self.assert_cli_sys_exit(args, 0)

    link_filename = FILENAME_FORMAT.format(step_name=self.test_step,
        keyid=self.gpg_key_D924E9)

    self.assertTrue(os.path.exists(link_filename))


  def test_main_no_command_arg(self):
    """Test CLI command with --no-command argument. """

    args = ["in_toto_run.py", "--step-name", self.test_step, "--key",
        self.rsa_key_path, "--no-command"]

    # Give wrong password whenever prompted.
    with mock.patch('in_toto.util.prompt_password', return_value='x'):
      self.assert_cli_sys_exit(args, 0)

    self.assertTrue(os.path.exists(self.test_link_rsa))

  def test_main_wrong_args(self):
    """Test CLI command with missing arguments. """

    wrong_args_list = [
      [],
      ["--step-name", "some"],
      ["--key", self.rsa_key_path],
      ["--", "echo", "blub"],
      ["--step-name", "test-step", "--key", self.rsa_key_path],
      ["--step-name", "--", "echo", "blub"],
      ["--key", self.rsa_key_path, "--", "echo", "blub"],
      ["--step-name", "test-step", "--key", self.rsa_key_path, "--"],
      ["--step-name", "test-step",
           "--key", self.rsa_key_path, "--gpg", "--", "echo", "blub"]
    ]

    for wrong_args in wrong_args_list:
      self.assert_cli_sys_exit(wrong_args, 2)
      self.assertFalse(os.path.exists(self.test_link_rsa))

  def test_main_wrong_key_exits(self):
    """Test CLI command with wrong key argument, exits and logs error """

    args = ["--step-name", self.test_step, "--key",
       "non-existing-key", "--", "echo", "test"]

    self.assert_cli_sys_exit(args, 1)
    self.assertFalse(os.path.exists(self.test_link_rsa))


if __name__ == "__main__":
  unittest.main()
