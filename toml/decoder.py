import datetime
import io
from os import linesep
import re
import sys

from toml.tz import TomlTz

if sys.version_info < (3,):
    _range = xrange  # noqa: F821
else:
    unicode = str
    _range = range
    basestring = str
    unichr = chr

try:
    FNFError = FileNotFoundError
except NameError:
    FNFError = IOError


class TomlDecodeError(Exception):
    """Base toml Exception / Error."""
    pass


# Matches a TOML number, which allows underscores for readability
_number_with_underscores = re.compile('([0-9])(_([0-9]))*')


def _strictly_valid_num(n):
    n = n.strip()
    if not n:
        return False
    if n[0] == '_':
        return False
    if n[-1] == '_':
        return False
    if "_." in n or "._" in n:
        return False
    if len(n) == 1:
        return True
    if n[0] == '0' and n[1] != '.':
        return False
    if n[0] == '+' or n[0] == '-':
        n = n[1:]
        if n[0] == '0' and n[1] != '.':
            return False
    if '__' in n:
        return False
    return True


def load(f, decoder=None):
    """Parses named file or files as toml and returns a dictionary

    Args:
        f: Path to the file to open, array of files to read into single dict
           or a file descriptor
        _dict: (optional) Specifies the class of the returned toml dictionary

    Returns:
        Parsed toml file represented as a dictionary

    Raises:
        TypeError -- When f is invalid type
        TomlDecodeError: Error while decoding toml
        IOError / FileNotFoundError -- When an array with no valid (existing)
        (Python 2 / Python 3)          file paths is passed
    """

    if isinstance(f, basestring):
        with io.open(f, encoding='utf-8') as ffile:
            return loads(ffile.read(), decoder)
    elif isinstance(f, list):
        from os import path as op
        from warnings import warn
        if not [path for path in f if op.exists(path)]:
            error_msg = "Load expects a list to contain filenames only."
            error_msg += linesep
            error_msg += ("The list needs to contain the path of at least one "
                          "existing file.")
            raise FNFError(error_msg)
        if decoder is None:
            decoder = TomlDecoder()
        d = decoder.get_empty_table()
        for l in f:
            if op.exists(l):
                d.update(load(l, decoder))
            else:
                warn("Non-existent filename in list with at least one valid "
                     "filename")
        return d
    else:
        try:
            return loads(f.read(), decoder)
        except AttributeError:
            raise TypeError("You can only load a file descriptor, filename or "
                            "list")


_groupname_re = re.compile(r'^[A-Za-z0-9_-]+$')


def loads(s, decoder=None):
    """Parses string as toml

    Args:
        s: String to be parsed
        _dict: (optional) Specifies the class of the returned toml dictionary

    Returns:
        Parsed toml file represented as a dictionary

    Raises:
        TypeError: When a non-string is passed
        TomlDecodeError: Error while decoding toml
    """

    implicitgroups = []
    if decoder is None:
        decoder = TomlDecoder()
    retval = decoder.get_empty_table()
    currentlevel = retval
    if not isinstance(s, basestring):
        raise TypeError("Expecting something like a string")

    if not isinstance(s, unicode):
        s = s.decode('utf8')

    sl = list(s)
    openarr = 0
    openstring = False
    openstrchar = ""
    multilinestr = False
    arrayoftables = False
    beginline = True
    keygroup = False
    keyname = 0
    for i, item in enumerate(sl):
        if item == '\r' and sl[i + 1] == '\n':
            sl[i] = ' '
            continue
        if keyname:
            if item == '\n':
                raise TomlDecodeError("Key name found without value."
                                      " Reached end of line.")
            if openstring:
                if item == openstrchar:
                    keyname = 2
                    openstring = False
                    openstrchar = ""
                continue
            elif keyname == 1:
                if item.isspace():
                    keyname = 2
                    continue
                elif item.isalnum() or item == '_' or item == '-':
                    continue
            elif keyname == 2 and item.isspace():
                continue
            if item == '=':
                keyname = 0
            else:
                raise TomlDecodeError("Found invalid character in key name: '" +
                                      item + "'. Try quoting the key name.")
        if item == "'" and openstrchar != '"':
            k = 1
            try:
                while sl[i - k] == "'":
                    k += 1
                    if k == 3:
                        break
            except IndexError:
                pass
            if k == 3:
                multilinestr = not multilinestr
                openstring = multilinestr
            else:
                openstring = not openstring
            if openstring:
                openstrchar = "'"
            else:
                openstrchar = ""
        if item == '"' and openstrchar != "'":
            oddbackslash = False
            k = 1
            tripquote = False
            try:
                while sl[i - k] == '"':
                    k += 1
                    if k == 3:
                        tripquote = True
                        break
                if k == 1 or (k == 3 and tripquote):
                    while sl[i - k] == '\\':
                        oddbackslash = not oddbackslash
                        k += 1
            except IndexError:
                pass
            if not oddbackslash:
                if tripquote:
                    multilinestr = not multilinestr
                    openstring = multilinestr
                else:
                    openstring = not openstring
            if openstring:
                openstrchar = '"'
            else:
                openstrchar = ""
        if item == '#' and (not openstring and not keygroup and
                            not arrayoftables):
            j = i
            try:
                while sl[j] != '\n':
                    sl[j] = ' '
                    j += 1
            except IndexError:
                break
        if item == '[' and (not openstring and not keygroup and
                            not arrayoftables):
            if beginline:
                if sl[i + 1] == '[':
                    arrayoftables = True
                else:
                    keygroup = True
            else:
                openarr += 1
        if item == ']' and not openstring:
            if keygroup:
                keygroup = False
            elif arrayoftables:
                if sl[i - 1] == ']':
                    arrayoftables = False
            else:
                openarr -= 1
        if item == '\n':
            if openstring or multilinestr:
                if not multilinestr:
                    raise TomlDecodeError("Unbalanced quotes")
                if ((sl[i - 1] == "'" or sl[i - 1] == '"') and (
                        sl[i - 2] == sl[i - 1])):
                    sl[i] = sl[i - 1]
                    if sl[i - 3] == sl[i - 1]:
                        sl[i - 3] = ' '
            elif openarr:
                sl[i] = ' '
            else:
                beginline = True
        elif beginline and sl[i] != ' ' and sl[i] != '\t':
            beginline = False
            if not keygroup and not arrayoftables:
                if sl[i] == '=':
                    raise TomlDecodeError("Found empty keyname. ")
                keyname = 1
    s = ''.join(sl)
    s = s.split('\n')
    multikey = None
    multilinestr = ""
    multibackslash = False
    for line in s:
        if not multilinestr or multibackslash or '\n' not in multilinestr:
            line = line.strip()
        if line == "" and (not multikey or multibackslash):
            continue
        if multikey:
            if multibackslash:
                multilinestr += line
            else:
                multilinestr += line
            multibackslash = False
            if len(line) > 2 and (line[-1] == multilinestr[0] and
                                  line[-2] == multilinestr[0] and
                                  line[-3] == multilinestr[0]):
                value, vtype = decoder.load_value(multilinestr)
                currentlevel[multikey] = value
                multikey = None
                multilinestr = ""
            else:
                k = len(multilinestr) - 1
                while k > -1 and multilinestr[k] == '\\':
                    multibackslash = not multibackslash
                    k -= 1
                if multibackslash:
                    multilinestr = multilinestr[:-1]
                else:
                    multilinestr += "\n"
            continue
        if line[0] == '[':
            arrayoftables = False
            if line[1] == '[':
                arrayoftables = True
                line = line[2:].split(']]', 1)
            else:
                line = line[1:].split(']', 1)
            if line[1].strip() != "":
                raise TomlDecodeError("Key group not on a line by itself.")
            groups = line[0].split('.')
            i = 0
            while i < len(groups):
                groups[i] = groups[i].strip()
                if groups[i][0] == '"' or groups[i][0] == "'":
                    groupstr = groups[i]
                    j = i + 1
                    while not groupstr[0] == groupstr[-1]:
                        j += 1
                        groupstr = '.'.join(groups[i:j])
                    groups[i] = groupstr[1:-1]
                    groups[i + 1:j] = []
                else:
                    if not _groupname_re.match(groups[i]):
                        raise TomlDecodeError("Invalid group name '" +
                                              groups[i] + "'. Try quoting it.")
                i += 1
            currentlevel = retval
            for i in _range(len(groups)):
                group = groups[i]
                if group == "":
                    raise TomlDecodeError("Can't have a keygroup with an empty "
                                          "name")
                try:
                    currentlevel[group]
                    if i == len(groups) - 1:
                        if group in implicitgroups:
                            implicitgroups.remove(group)
                            if arrayoftables:
                                raise TomlDecodeError("An implicitly defined "
                                                      "table can't be an array")
                        elif arrayoftables:
                            currentlevel[group].append(decoder.get_empty_table()
                                                       )
                        else:
                            raise TomlDecodeError("What? " + group +
                                                  " already exists?" +
                                                  str(currentlevel))
                except TypeError:
                    currentlevel = currentlevel[-1]
                    try:
                        currentlevel[group]
                    except KeyError:
                        currentlevel[group] = decoder.get_empty_table()
                        if i == len(groups) - 1 and arrayoftables:
                            currentlevel[group] = [decoder.get_empty_table()]
                except KeyError:
                    if i != len(groups) - 1:
                        implicitgroups.append(group)
                    currentlevel[group] = decoder.get_empty_table()
                    if i == len(groups) - 1 and arrayoftables:
                        currentlevel[group] = [decoder.get_empty_table()]
                currentlevel = currentlevel[group]
                if arrayoftables:
                    try:
                        currentlevel = currentlevel[-1]
                    except KeyError:
                        pass
        elif line[0] == "{":
            if line[-1] != "}":
                raise TomlDecodeError("Line breaks are not allowed in inline"
                                      "objects")
            decoder.load_inline_object(line, currentlevel, multikey,
                                       multibackslash)
        elif "=" in line:
            ret = decoder.load_line(line, currentlevel, multikey,
                                    multibackslash)
            if ret is not None:
                multikey, multilinestr, multibackslash = ret
    return retval


def _load_date(val):
    microsecond = 0
    tz = None
    try:
        if len(val) > 19:
            if val[19] == '.':
                microsecond = int(val[20:26])
                if len(val) > 26:
                    tz = TomlTz(val[26:32])
            else:
                tz = TomlTz(val[19:25])
    except ValueError:
        tz = None
    try:
        d = datetime.datetime(
            int(val[:4]), int(val[5:7]),
            int(val[8:10]), int(val[11:13]),
            int(val[14:16]), int(val[17:19]), microsecond, tz)
    except ValueError:
        return None
    return d


def _load_unicode_escapes(v, hexbytes, prefix):
    hexchars = ['0', '1', '2', '3', '4', '5', '6', '7',
                '8', '9', 'a', 'b', 'c', 'd', 'e', 'f']
    skip = False
    i = len(v) - 1
    while i > -1 and v[i] == '\\':
        skip = not skip
        i -= 1
    for hx in hexbytes:
        if skip:
            skip = False
            i = len(hx) - 1
            while i > -1 and hx[i] == '\\':
                skip = not skip
                i -= 1
            v += prefix
            v += hx
            continue
        hxb = ""
        i = 0
        hxblen = 4
        if prefix == "\\U":
            hxblen = 8
        while i < hxblen:
            try:
                if not hx[i].lower() in hexchars:
                    raise IndexError("This is a hack")
            except IndexError:
                raise TomlDecodeError("Invalid escape sequence")
            hxb += hx[i].lower()
            i += 1
        v += unichr(int(hxb, 16))
        v += unicode(hx[len(hxb):])
    return v


# Unescape TOML string values.

# content after the \
_escapes = ['0', 'b', 'f', 'n', 'r', 't', '"']
# What it should be replaced by
_escapedchars = ['\0', '\b', '\f', '\n', '\r', '\t', '\"']
# Used for substitution
_escape_to_escapedchars = dict(zip(_escapes, _escapedchars))


def _unescape(v):
    """Unescape characters in a TOML string."""
    i = 0
    backslash = False
    while i < len(v):
        if backslash:
            backslash = False
            if v[i] in _escapes:
                v = v[:i - 1] + _escape_to_escapedchars[v[i]] + v[i + 1:]
            elif v[i] == '\\':
                v = v[:i - 1] + v[i:]
            elif v[i] == 'u' or v[i] == 'U':
                i += 1
            else:
                raise TomlDecodeError("Reserved escape sequence used")
            continue
        elif v[i] == '\\':
            backslash = True
        i += 1
    return v


class InlineTableDict(object):
    """Sentinel subclass of dict for inline tables."""


class TomlDecoder(object):

    def __init__(self, _dict=dict):
        self._dict = _dict

    def get_empty_table(self):
        return self._dict()

    def get_empty_inline_table(self):
        class DynamicInlineTableDict(self._dict, InlineTableDict):
            """Concrete sentinel subclass for inline tables.
            It is a subclass of _dict which is passed in dynamically at load
            time

            It is also a subclass of InlineTableDict
            """

        return DynamicInlineTableDict()

    def load_inline_object(self, line, currentlevel, multikey=False,
                           multibackslash=False):
        candidate_groups = line[1:-1].split(",")
        groups = []
        if len(candidate_groups) == 1 and not candidate_groups[0].strip():
            candidate_groups.pop()
        while len(candidate_groups) > 0:
            candidate_group = candidate_groups.pop(0)
            try:
                _, value = candidate_group.split('=', 1)
            except ValueError:
                raise TomlDecodeError("Invalid inline table encountered")
            value = value.strip()
            if ((value[0] == value[-1] and value[0] in ('"', "'")) or (
                    value[0] in '-0123456789' or
                    value in ('true', 'false') or
                    (value[0] == "[" and value[-1] == "]"))):
                groups.append(candidate_group)
            else:
                candidate_groups[0] = (candidate_group + "," +
                                       candidate_groups[0])
        for group in groups:
            status = self.load_line(group, currentlevel, multikey,
                                    multibackslash)
            if status is not None:
                break

    def load_line(self, line, currentlevel, multikey, multibackslash):
        i = 1
        pair = line.split('=', i)
        strictly_valid = _strictly_valid_num(pair[-1])
        if _number_with_underscores.match(pair[-1]):
            pair[-1] = pair[-1].replace('_', '')
        while len(pair[-1]) and (pair[-1][0] != ' ' and pair[-1][0] != '\t' and
                                 pair[-1][0] != "'" and pair[-1][0] != '"' and
                                 pair[-1][0] != '[' and pair[-1][0] != '{' and
                                 pair[-1] != 'true' and pair[-1] != 'false'):
            try:
                float(pair[-1])
                break
            except ValueError:
                pass
            if _load_date(pair[-1]) is not None:
                break
            i += 1
            prev_val = pair[-1]
            pair = line.split('=', i)
            if prev_val == pair[-1]:
                raise TomlDecodeError("Invalid date or number")
            if strictly_valid:
                strictly_valid = _strictly_valid_num(pair[-1])
        pair = ['='.join(pair[:-1]).strip(), pair[-1].strip()]
        if (pair[0][0] == '"' or pair[0][0] == "'") and \
                (pair[0][-1] == '"' or pair[0][-1] == "'"):
            pair[0] = pair[0][1:-1]
        if len(pair[1]) > 2 and ((pair[1][0] == '"' or pair[1][0] == "'") and
                                 pair[1][1] == pair[1][0] and
                                 pair[1][2] == pair[1][0] and
                                 not (len(pair[1]) > 5 and
                                      pair[1][-1] == pair[1][0] and
                                      pair[1][-2] == pair[1][0] and
                                      pair[1][-3] == pair[1][0])):
            k = len(pair[1]) - 1
            while k > -1 and pair[1][k] == '\\':
                multibackslash = not multibackslash
                k -= 1
            if multibackslash:
                multilinestr = pair[1][:-1]
            else:
                multilinestr = pair[1] + "\n"
            multikey = pair[0]
        else:
            value, vtype = self.load_value(pair[1], strictly_valid)
        try:
            currentlevel[pair[0]]
            raise TomlDecodeError("Duplicate keys!")
        except KeyError:
            if multikey:
                return multikey, multilinestr, multibackslash
            else:
                currentlevel[pair[0]] = value
        except:
            raise TomlDecodeError("Duplicate keys!")

    def load_value(self, v, strictly_valid=True):
        if not v:
            raise TomlDecodeError("Empty value is invalid")
        if v == 'true':
            return (True, "bool")
        elif v == 'false':
            return (False, "bool")
        elif v[0] == '"':
            testv = v[1:].split('"')
            if testv[0] == '' and testv[1] == '':
                testv = testv[2:-2]
            closed = False
            for tv in testv:
                if tv == '':
                    closed = True
                else:
                    oddbackslash = False
                    try:
                        i = -1
                        j = tv[i]
                        while j == '\\':
                            oddbackslash = not oddbackslash
                            i -= 1
                            j = tv[i]
                    except IndexError:
                        pass
                    if not oddbackslash:
                        if closed:
                            raise TomlDecodeError("Stuff after closed string. "
                                                  "WTF?")
                        else:
                            closed = True
            escapeseqs = v.split('\\')[1:]
            backslash = False
            for i in escapeseqs:
                if i == '':
                    backslash = not backslash
                else:
                    if i[0] not in _escapes and (i[0] != 'u' and i[0] != 'U' and
                                                 not backslash):
                        raise TomlDecodeError("Reserved escape sequence used")
                    if backslash:
                        backslash = False
            for prefix in ["\\u", "\\U"]:
                if prefix in v:
                    hexbytes = v.split(prefix)
                    v = _load_unicode_escapes(hexbytes[0], hexbytes[1:], prefix)
            v = _unescape(v)
            if v[1] == '"' and (len(v) < 3 or v[1] == v[2]):
                v = v[2:-2]
            return (v[1:-1], "str")
        elif v[0] == "'":
            if v[1] == "'" and (len(v) < 3 or v[1] == v[2]):
                v = v[2:-2]
            return (v[1:-1], "str")
        elif v[0] == '[':
            return (self.load_array(v), "array")
        elif v[0] == '{':
            inline_object = self.get_empty_inline_table()
            self.load_inline_object(v, inline_object)
            return (inline_object, "inline_object")
        else:
            parsed_date = _load_date(v)
            if parsed_date is not None:
                return (parsed_date, "date")
            if not strictly_valid:
                raise TomlDecodeError("Weirdness with leading zeroes or "
                                      "underscores in your number.")
            itype = "int"
            neg = False
            if v[0] == '-':
                neg = True
                v = v[1:]
            elif v[0] == '+':
                v = v[1:]
            v = v.replace('_', '')
            if '.' in v or 'e' in v or 'E' in v:
                if '.' in v and v.split('.', 1)[1] == '':
                    raise TomlDecodeError("This float is missing digits after "
                                          "the point")
                if v[0] not in '0123456789':
                    raise TomlDecodeError("This float doesn't have a leading "
                                          "digit")
                v = float(v)
                itype = "float"
            else:
                v = int(v)
            if neg:
                return (0 - v, itype)
            return (v, itype)

    def load_array(self, a):
        atype = None
        retval = []
        a = a.strip()
        if '[' not in a[1:-1] or "" != a[1:-1].split('[')[0].strip():
            strarray = False
            tmpa = a[1:-1].strip()
            if tmpa != '' and (tmpa[0] == '"' or tmpa[0] == "'"):
                strarray = True
            if not a[1:-1].strip().startswith('{'):
                a = a[1:-1].split(',')
            else:
                # a is an inline object, we must find the matching parenthesis
                # to define groups
                new_a = []
                start_group_index = 1
                end_group_index = 2
                in_str = False
                while end_group_index < len(a[1:]):
                    if a[end_group_index] == '"' or a[end_group_index] == "'":
                        in_str = not in_str
                    if in_str or a[end_group_index] != '}':
                        end_group_index += 1
                        continue

                    # Increase end_group_index by 1 to get the closing bracket
                    end_group_index += 1

                    new_a.append(a[start_group_index:end_group_index])

                    # The next start index is at least after the closing
                    # bracket, a closing bracket can be followed by a comma
                    # since we are in an array.
                    start_group_index = end_group_index + 1
                    while (start_group_index < len(a[1:]) and
                           a[start_group_index] != '{'):
                        start_group_index += 1
                    end_group_index = start_group_index + 1
                a = new_a
            b = 0
            if strarray:
                while b < len(a) - 1:
                    ab = a[b].strip()
                    while ab[-1] != ab[0] or (len(ab) > 2 and
                                              ab[0] == ab[1] == ab[2] and
                                              ab[-2] != ab[0] and
                                              ab[-3] != ab[0]):
                        a[b] = a[b] + ',' + a[b + 1]
                        ab = a[b].strip()
                        if b < len(a) - 2:
                            a = a[:b + 1] + a[b + 2:]
                        else:
                            a = a[:b + 1]
                    b += 1
        else:
            al = list(a[1:-1])
            a = []
            openarr = 0
            j = 0
            for i in _range(len(al)):
                if al[i] == '[':
                    openarr += 1
                elif al[i] == ']':
                    openarr -= 1
                elif al[i] == ',' and not openarr:
                    a.append(''.join(al[j:i]))
                    j = i + 1
            a.append(''.join(al[j:]))
        for i in _range(len(a)):
            a[i] = a[i].strip()
            if a[i] != '':
                nval, ntype = self.load_value(a[i])
                if atype:
                    if ntype != atype:
                        raise TomlDecodeError("Not a homogeneous array")
                else:
                    atype = ntype
                retval.append(nval)
        return retval
