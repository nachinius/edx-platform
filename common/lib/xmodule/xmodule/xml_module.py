from collections import MutableMapping
from xmodule.x_module import XModuleDescriptor
from xmodule.modulestore import Location
from lxml import etree
import copy
import logging
from collections import namedtuple
from fs.errors import ResourceNotFoundError
import os

log = logging.getLogger(__name__)

# TODO (cpennington): This was implemented in an attempt to improve performance,
# but the actual improvement wasn't measured (and it was implemented late at night).
# We should check if it hurts, and whether there's a better way of doing lazy loading


class LazyLoadingDict(MutableMapping):
    """
    A dictionary object that lazily loads its contents from a provided
    function on reads (of members that haven't already been set).
    """

    def __init__(self, loader):
        '''
        On the first read from this dictionary, it will call loader() to
        populate its contents.  loader() must return something dict-like. Any
        elements set before the first read will be preserved.
        '''
        self._contents = {}
        self._loaded = False
        self._loader = loader
        self._deleted = set()

    def __getitem__(self, name):
        if not (self._loaded or name in self._contents or name in self._deleted):
            self.load()

        return self._contents[name]

    def __setitem__(self, name, value):
        self._contents[name] = value
        self._deleted.discard(name)

    def __delitem__(self, name):
        del self._contents[name]
        self._deleted.add(name)

    def __contains__(self, name):
        self.load()
        return name in self._contents

    def __len__(self):
        self.load()
        return len(self._contents)

    def __iter__(self):
        self.load()
        return iter(self._contents)

    def __repr__(self):
        self.load()
        return repr(self._contents)

    def load(self):
        if self._loaded:
            return

        loaded_contents = self._loader()
        loaded_contents.update(self._contents)
        self._contents = loaded_contents
        self._loaded = True


_AttrMapBase = namedtuple('_AttrMap', 'metadata_key to_metadata from_metadata')


class AttrMap(_AttrMapBase):
    """
    A class that specifies a metadata_key, and two functions:

        to_metadata: convert value from the xml representation into
            an internal python representation

        from_metadata: convert the internal python representation into
            the value to store in the xml.
    """
    def __new__(_cls, metadata_key,
                to_metadata=lambda x: x,
                from_metadata=lambda x: x):
        return _AttrMapBase.__new__(_cls, metadata_key, to_metadata, from_metadata)


class XmlDescriptor(XModuleDescriptor):
    """
    Mixin class for standardized parsing of from xml
    """

    # Extension to append to filename paths
    filename_extension = 'xml'

    # The attributes will be removed from the definition xml passed
    # to definition_from_xml, and from the xml returned by definition_to_xml
    metadata_attributes = ('format', 'graceperiod', 'showanswer', 'rerandomize',
        'start', 'due', 'graded', 'display_name', 'url_name', 'hide_from_toc',
        # VS[compat] Remove once unused.
        'name', 'slug')


    # A dictionary mapping xml attribute names AttrMaps that describe how
    # to import and export them
    xml_attribute_map = {
        # type conversion: want True/False in python, "true"/"false" in xml
        'graded': AttrMap('graded',
                          lambda val: val == 'true',
                          lambda val: str(val).lower()),
    }


    # VS[compat].  Backwards compatibility code that can go away after
    # importing 2012 courses.
    # A set of metadata key conversions that we want to make
    metadata_translations = {
        'slug' : 'url_name',
        'name' : 'display_name',
        }

    @classmethod
    def _translate(cls, key):
        'VS[compat]'
        return cls.metadata_translations.get(key, key)


    @classmethod
    def definition_from_xml(cls, xml_object, system):
        """
        Return the definition to be passed to the newly created descriptor
        during from_xml

        xml_object: An etree Element
        """
        raise NotImplementedError(
            "%s does not implement definition_from_xml" % cls.__name__)

    @classmethod
    def clean_metadata_from_xml(cls, xml_object):
        """
        Remove any attribute named in cls.metadata_attributes from the supplied
        xml_object
        """
        for attr in cls.metadata_attributes:
            if xml_object.get(attr) is not None:
                del xml_object.attrib[attr]

    @classmethod
    def file_to_xml(cls, file_object):
        """
        Used when this module wants to parse a file object to xml
        that will be converted to the definition.

        Returns an lxml Element
        """
        return etree.parse(file_object).getroot()

    @classmethod
    def from_xml(cls, xml_data, system, org=None, course=None):
        """
        Creates an instance of this descriptor from the supplied xml_data.
        This may be overridden by subclasses

        xml_data: A string of xml that will be translated into data and children for
            this module
        system: A DescriptorSystem for interacting with external resources
        org and course are optional strings that will be used in the generated modules
            url identifiers
        """
        xml_object = etree.fromstring(xml_data)
        # VS[compat] -- just have the url_name lookup once translation is done
        slug = xml_object.get('url_name', xml_object.get('slug'))
        location = Location('i4x', org, course, xml_object.tag, slug)

        def metadata_loader():
            metadata = {}
            for attr in cls.metadata_attributes:
                val = xml_object.get(attr)
                if val is not None:
                    # VS[compat].  Remove after all key translations done
                    attr = cls._translate(attr)

                    attr_map = cls.xml_attribute_map.get(attr, AttrMap(attr))
                    metadata[attr_map.metadata_key] = attr_map.to_metadata(val)
            return metadata

        def definition_loader():
            filename = xml_object.get('filename')
            if filename is None:
                definition_xml = copy.deepcopy(xml_object)
            else:
                filepath = cls._format_filepath(xml_object.tag, filename)

                # VS[compat]
                # TODO (cpennington): If the file doesn't exist at the right path,
                # give the class a chance to fix it up. The file will be written out again
                # in the correct format.
                # This should go away once the CMS is online and has imported all current (fall 2012)
                # courses from xml
                if not system.resources_fs.exists(filepath) and hasattr(cls, 'backcompat_paths'):
                    candidates = cls.backcompat_paths(filepath)
                    for candidate in candidates:
                        if system.resources_fs.exists(candidate):
                            filepath = candidate
                            break

                try:
                    with system.resources_fs.open(filepath) as file:
                        definition_xml = cls.file_to_xml(file)
                except (ResourceNotFoundError, etree.XMLSyntaxError):
                    msg = 'Unable to load file contents at path %s for item %s' % (filepath, location.url())
                    log.exception(msg)
                    system.error_handler(msg)
                    # if error_handler didn't reraise, work around problem.
                    error_elem = etree.Element('error')
                    error_elem.text = msg
                    return {'data': etree.tostring(error_elem)}

            cls.clean_metadata_from_xml(definition_xml)
            return cls.definition_from_xml(definition_xml, system)

        return cls(
            system,
            LazyLoadingDict(definition_loader),
            location=location,
            metadata=LazyLoadingDict(metadata_loader),
        )

    @classmethod
    def _format_filepath(cls, category, name):
        return u'{category}/{name}.{ext}'.format(category=category,
                                                 name=name,
                                                 ext=cls.filename_extension)

    @classmethod
    def split_to_file(cls, xml_object):
        '''
        Decide whether to write this object to a separate file or not.

        xml_object: an xml definition of an instance of cls.

        This default implementation will split if this has more than 7
        descendant tags.

        Can be overridden by subclasses.
        '''
        return len(list(xml_object.iter())) > 7

    def export_to_xml(self, resource_fs):
        """
        Returns an xml string representing this module, and all modules
        underneath it.  May also write required resources out to resource_fs

        Assumes that modules have single parentage (that no module appears twice
        in the same course), and that it is thus safe to nest modules as xml
        children as appropriate.

        The returned XML should be able to be parsed back into an identical
        XModuleDescriptor using the from_xml method with the same system, org,
        and course

        resource_fs is a pyfilesystem object (from the fs package)
        """

        # Get the definition
        xml_object = self.definition_to_xml(resource_fs)
        self.__class__.clean_metadata_from_xml(xml_object)

        # Set the tag first, so it's right if writing to a file
        xml_object.tag = self.category

        # Write it to a file if necessary
        if self.split_to_file(xml_object):
            # Put this object in it's own file
            filepath = self.__class__._format_filepath(self.category, self.name)
            resource_fs.makedir(os.path.dirname(filepath), allow_recreate=True)
            with resource_fs.open(filepath, 'w') as file:
                file.write(etree.tostring(xml_object, pretty_print=True))
            # ...and remove all of its children here
            for child in xml_object:
                xml_object.remove(child)
            # also need to remove the text of this object.
            xml_object.text = ''
            # and the tail for good measure...
            xml_object.tail = ''


            xml_object.set('filename', self.name)

        # Add the metadata
        xml_object.set('url_name', self.name)
        for attr in self.metadata_attributes:
            attr_map = self.xml_attribute_map.get(attr, AttrMap(attr))
            metadata_key = attr_map.metadata_key

            if (metadata_key not in self.metadata or
                metadata_key in self._inherited_metadata):
                continue

            val = attr_map.from_metadata(self.metadata[metadata_key])
            xml_object.set(attr, val)

        # Now we just have to make it beautiful
        return etree.tostring(xml_object, pretty_print=True)

    def definition_to_xml(self, resource_fs):
        """
        Return a new etree Element object created from this modules definition.
        """
        raise NotImplementedError(
            "%s does not implement definition_to_xml" % self.__class__.__name__)
