##############################################################################
#
# Copyright (c) 2002, 2003 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Objects that can describe a ZConfig schema."""

import ZConfig


try:
    True
except NameError:
    True = 1
    False = 0


class UnboundedThing:
    def __lt__(self, other):
        return False

    def __le__(self, other):
        return isinstance(other, self.__class__)

    def __gt__(self, other):
        return True

    def __ge__(self, other):
        return True

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not isinstance(other, self.__class__)

    def __repr__(self):
        return "<Unbounded>"

Unbounded = UnboundedThing()


class ValueInfo:
    def __init__(self, value, position):
        self.value = value
        # position is (lineno, colno, url)
        self.position = position

    def convert(self, datatype):
        try:
            return datatype(self.value)
        except ValueError, e:
            raise ZConfig.DataConversionError(e, self.value, self.position)


class BaseInfo:
    """Information about a single configuration key."""

    description = None
    example = None
    metadefault = None

    def __init__(self, name, datatype, minOccurs, maxOccurs, handler,
                 attribute):
        if maxOccurs is not None and maxOccurs < 1:
            if maxOccurs < 1:
                raise ZConfig.SchemaError(
                    "maxOccurs must be at least 1")
            if minOccurs is not None and minOccurs < maxOccurs:
                raise ZConfig.SchemaError(
                    "minOccurs must be at least maxOccurs")
        self.name = name
        self.datatype = datatype
        self.minOccurs = minOccurs
        self.maxOccurs = maxOccurs
        self.handler = handler
        self.attribute = attribute

    def __repr__(self):
        clsname = self.__class__.__name__
        return "<%s for %s>" % (clsname, `self.name`)

    def istypegroup(self):
        return False

    def ismulti(self):
        return self.maxOccurs > 1

    def issection(self):
        return False


class KeyInfo(BaseInfo):
    def __init__(self, name, datatype, minOccurs, maxOccurs, handler,
                 attribute):
        assert minOccurs is not None
        BaseInfo.__init__(self, name, datatype, minOccurs, maxOccurs,
                          handler, attribute)
        self._finished = False
        self._default = None

    def finish(self):
        if self._finished:
            raise ZConfig.SchemaError(
                "cannot finish KeyInfo more than once")
        self._finished = True

    def adddefault(self, value, position):
        if self._finished:
            raise ZConfig.SchemaError(
                "cannot add default values to finished KeyInfo")
        value = ValueInfo(value, position)
        if self.maxOccurs > 1:
            if self._default is None:
                self._default = [value]
            else:
                self._default.append(value)
        elif self._default is not None:
            raise ZConfig.SchemaError(
                "cannot set more than one default to key with maxOccurs == 1")
        else:
            self._default = value

    def getdefault(self):
        if not self._finished:
            raise ZConfig.SchemaError(
                "cannot get default value of key before KeyInfo"
                " has been completely initialized")
        if self._default is None and self.maxOccurs > 1:
            return []
        else:
            return self._default


class SectionInfo(BaseInfo):
    def __init__(self, name, sectiontype, minOccurs, maxOccurs, handler,
                 attribute):
        # name        - name of the section; one of '*', '+', or name1
        # sectiontype - SectionType instance
        # minOccurs   - minimum number of occurances of the section
        # maxOccurs   - maximum number of occurances; if > 1, name
        #               must be '*' or '+'
        # handler     - handler name called when value(s) must take effect,
        #               or None
        # attribute   - name of the attribute on the SectionValue object
        if maxOccurs > 1:
            if name not in ('*', '+'):
                raise ZConfig.SchemaError(
                    "sections which can occur more than once must"
                    " use a name of '*' or '+'")
            if not attribute:
                raise ZConfig.SchemaError(
                    "sections which can occur more than once must"
                    " specify a target attribute name")
        if sectiontype.istypegroup():
            datatype = None
        else:
            datatype = sectiontype.datatype
        BaseInfo.__init__(self, name, datatype,
                          minOccurs, maxOccurs, handler, attribute)
        self.sectiontype = sectiontype

    def __repr__(self):
        clsname = self.__class__.__name__
        return "<%s for %s (%s)>" % (
            clsname, self.sectiontype.name, `self.name`)

    def issection(self):
        return True

    def allowUnnamed(self):
        return self.name == "*"

    def isAllowedName(self, name):
        if name == "*" or name == "+":
            return False
        elif self.name == "+":
            return name and True or False
        elif not name:
            return self.name == "*"
        else:
            return name == self.name

    def getdefault(self):
        # sections cannot have defaults
        if self.maxOccurs > 1:
            return []
        else:
            return None


class GroupType:
    def __init__(self, name):
        self._subtypes = {}
        self.name = name

    def addsubtype(self, type):
        self._subtypes[type.name] = type

    def getsubtype(self, name):
        try:
            return self._subtypes[name]
        except KeyError:
            raise ZConfig.SchemaError("no subtype %s in group %s"
                                      % (`name`, `self.name`))

    def getsubtypenames(self):
        L = self._subtypes.keys()
        L.sort()
        return L

    def istypegroup(self):
        return True


class SectionType:
    def __init__(self, name, keytype, valuetype, datatype, registry, types):
        # name      - name of the section, or '*' or '+'
        # datatype  - type for the section itself
        # keytype   - type for the keys themselves
        # valuetype - default type for key values
        self.name = name
        self.datatype = datatype
        self.keytype = keytype
        self.valuetype = valuetype
        self.handler = None
        self.registry = registry
        self._children = []    # [(key, info), ...]
        self._attrmap = {}     # {attribute: index, ...}
        self._keymap = {}      # {key: index, ...}
        self._types = types

    def gettype(self, name):
        n = name.lower()
        try:
            return self._types[n]
        except KeyError:
            raise ZConfig.SchemaError("unknown type name: " + `name`)

    def gettypenames(self):
        return self._types.keys()

    def __len__(self):
        return len(self._children)

    def __getitem__(self, index):
        return self._children[index]

    def _add_child(self, key, info):
        # check naming constraints
        assert key or info.attribute
        if key and self._keymap.has_key(key):
            raise ZConfig.SchemaError(
                "child name %s already used" % key)
        if info.attribute and self._attrmap.has_key(info.attribute):
            raise ZConfig.SchemaError(
                "child attribute name %s already used" % info.attribute)
        # a-ok, add the item to the appropriate maps
        if info.attribute:
            self._attrmap[info.attribute] = len(self._children)
        if key:
            self._keymap[key] = len(self._children)
        self._children.append((key, info))

    def addkey(self, keyinfo):
        self._add_child(keyinfo.name, keyinfo)

    def addsection(self, name, sectinfo):
        assert name not in ("*", "+")
        self._add_child(name, sectinfo)

    def getinfo(self, key):
        if not key:
            raise ZConfig.ConfigurationError(
                "cannot match a key without a name")
        index = self._keymap.get(key)
        if index is None:
            raise ZConfig.ConfigurationError("no key matching " + `key`)
        else:
            return self._children[index][1]

    def getchildnames(self):
        return [key for (key, info) in self._children]

    def getrequiredtypes(self):
        d = {}
        if self.name:
            d[self.name] = 1
        stack = [self]
        while stack:
            info = stack.pop()
            for key, ci in info._children:
                if ci.issection():
                    t = ci.sectiontype
                    if not d.has_key(t.name):
                        d[t.name] = 1
                        stack.append(t)
        return d.keys()

    def getsectionindex(self, type, name):
        index = -1
        for key, info in self._children:
            index += 1
            if key:
                if key == name:
                    if not info.issection():
                        raise ZConfig.ConfigurationError(
                            "section name %s already in use for key" % key)
                    st = info.sectiontype
                    if st.istypegroup():
                        try:
                            st = st.getsubtype(type)
                        except ZConfig.ConfigurationError:
                            raise ZConfig.ConfigurationError(
                                "section type %s not allowed for name %s"
                                % (`type`, `key`))
                    if not st.name == type:
                        raise ZConfig.ConfigurationError(
                            "name %s must be used for a %s section"
                            % (`name`, `st.name`))
                    return index
            # else must be a section or a sectiongroup:
            elif info.sectiontype.name == type:
                if not (name or info.allowUnnamed()):
                    raise ZConfig.ConfigurationError(
                        `type` + " sections must be named")
                return index
            elif info.sectiontype.istypegroup():
                st = info.sectiontype
                if st.name == type:
                    raise ZConfig.ConfigurationError(
                        "cannot define section with a sectiongroup type")
                try:
                    st = st.getsubtype(type)
                except ZConfig.ConfigurationError:
                    # not this one; maybe a different one
                    pass
                else:
                    return index
        raise ZConfig.ConfigurationError("no matching section defined")

    def getsectioninfo(self, type, name):
        i = self.getsectionindex(type, name)
        st = self._children[i][1]
        if st.istypegroup():
            st = st.gettype(type)
        return st

    def istypegroup(self):
        return False


class SchemaType(SectionType):
    def __init__(self, name, keytype, valuetype, datatype, handler, url,
                 registry):
        SectionType.__init__(self, name, keytype, valuetype, datatype,
                             registry, {})
        self.handler = handler
        self.url = url

    def addtype(self, typeinfo):
        n = typeinfo.name.lower()
        if self._types.has_key(n):
            raise ZConfig.SchemaError("type name cannot be redefined: "
                                             + `typeinfo.name`)
        self._types[n] = typeinfo

    def allowUnnamed(self):
        return True

    def isAllowedName(self, name):
        return False

    def issection(self):
        return True

    def getunusedtypes(self):
        alltypes = self.gettypenames()
        reqtypes = self.getrequiredtypes()
        for n in reqtypes:
            alltypes.remove(n)
        if self.name and self.name in alltypes:
            alltypes.remove(self.name)
        return alltypes

    def createSectionType(self, name, keytype, valuetype, datatype):
        t = SectionType(name, keytype, valuetype, datatype,
                        self.registry, self._types)
        self.addtype(t)
        return t