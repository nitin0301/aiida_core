"""Manage code objects with lazy loading of the db env"""
import enum
import os

from aiida.cmdline.utils.decorators import with_dbenv
from aiida.utils.error_accumulator import ErrorAccumulator


class CodeBuilder(object):
    """Build a code with validation of attribute combinations"""

    def __init__(self, **kwargs):
        self._code_spec = kwargs
        self._err_acc = ErrorAccumulator(self.CodeValidationError)

    def validate(self, raise_error=True):
        self._err_acc.run(self.validate_code_type)
        self._err_acc.run(self.validate_upload)
        self._err_acc.run(self.validate_installed)
        return self._err_acc.result(raise_error=self.CodeValidationError if raise_error else False)

    @with_dbenv()
    def new(self):
        """Build and return a new code instance (not stored)"""
        self.validate()

        from aiida.orm import Code

        # Will be used at the end to check if all keys are known
        passed_keys = set(self._code_spec.keys())
        used = set()

        if self.code_type == self.CodeType.STORE_AND_UPLOAD:
            file_list = [
                os.path.realpath(os.path.join(self.code_folder, f))
                for f in os.listdir(self._get_and_count('code_folder', used))
            ]
            code = Code(local_executable=self._get_and_count('code_rel_path', used), files=file_list)
        else:
            code = Code(
                remote_computer_exec=(self._get_and_count('computer', used),
                                      self._get_and_count('remote_abs_path', used)))

        code.label = self._get_and_count('label', used)
        code.description = self._get_and_count('description', used)
        code.set_input_plugin_name(self._get_and_count('input_plugin', used).name)
        code.set_prepend_text(self._get_and_count('prepend_text', used))
        code.set_append_text(self._get_and_count('append_text', used))

        # Complain if there are keys that are passed but not used
        if passed_keys - used:
            raise self.CodeValidationError('Unknown parameters passed to the CodeBuilder: {}'.format(
                ", ".join(sorted(passed_keys - used))))

        return code

    def __getattr__(self, key):
        """Access code attributes used to build the code"""
        if not key.startswith('_'):
            try:
                return self._code_spec[key]
            except KeyError:
                raise self.CodeValidationError(key + ' not set')
        return None

    def _get(self, key):
        """
        Return a spec, or None if not defined

        :param key: name of a code spec
        """
        return self._code_spec.get(key)

    def _get_and_count(self, key, used):
        """
        Return a spec, or raise if not defined.
        Moreover, add the key to the 'used' dict.

        :param key: name of a code spec
        :param used: should be a set of keys that you want to track.
           ``key`` will be added to this set if the value exists in the spec and can be retrieved.
        """
        retval = self.__getattr__(key)
        ## I first get a retval, so if I get an exception, I don't add it to the 'used' set
        used.add(key)
        return retval

    def __setattr__(self, key, value):
        if not key.startswith('_'):
            self._set_code_attr(key, value)
        super(CodeBuilder, self).__setattr__(key, value)

    def _set_code_attr(self, key, value):
        """Set a code attribute if it passes validation."""
        backup = self._code_spec.copy()
        self._code_spec[key] = value
        success, _ = self.validate(raise_error=False)
        if not success:
            self._code_spec = backup
            self.validate()

    def validate_code_type(self):
        """Make sure the code type is set correctly"""
        if self._get('code_type') and self.code_type not in self.CodeType:
            raise self.CodeValidationError('invalid code type: must be one of {}, not {}'.format(
                list(self.CodeType), self.code_type))

    def validate_upload(self):
        """If the code is stored and uploaded, catch invalid on-computer attributes"""
        messages = []
        if self._get('code_type') == self.CodeType.STORE_AND_UPLOAD:
            if self._get('computer'):
                messages.append('invalid option for store-and-upload code: "computer"')
            if self._get('remote_abs_path'):
                messages.append('invalid option for store-and-upload code: "remote_abs_path"')
        if messages:
            raise self.CodeValidationError('{}'.format(messages))

    def validate_installed(self):
        """If the code is on-computer, catch invalid store-and-upload attributes"""
        messages = []
        if self._get('code_type') == self.CodeType.ON_COMPUTER:
            if self._get('code_folder'):
                messages.append('invalid options for on-computer code: "code_folder"')
            if self._get('code_rel_path'):
                messages.append('invalid options for on-computer code: "code_rel_path"')
        if messages:
            raise self.CodeValidationError('{}'.format(messages))

    class CodeValidationError(Exception):
        """
        A CodeBuilder instance may raise this

         * when asked to instanciate a code with missing or invalid code attributes
         * when asked for a code attibute that has not been set yet
        """

        def __init__(self, msg):
            super(CodeBuilder.CodeValidationError, self).__init__()
            self.msg = msg

        def __str__(self):
            return self.msg

        def __repr__(self):
            return '<CodeValidationError: {}>'.format(self)

    # pylint: disable=too-few-public-methods
    class CodeType(enum.Enum):
        STORE_AND_UPLOAD = 'store in the db and upload'
        ON_COMPUTER = 'on computer'
