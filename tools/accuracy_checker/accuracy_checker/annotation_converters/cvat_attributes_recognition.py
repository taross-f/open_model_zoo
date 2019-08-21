from .format_converter import FileBasedAnnotationConverter, ConverterReturn
from ..representation import ClassificationAnnotation, ContainerAnnotation
from ..topology_types import ImageClassification
from ..utils import read_xml, check_file_existence
from ..config import StringField, PathField, ConfigError


class CVATForAttributesRecognition(FileBasedAnnotationConverter):
    __provider__ = 'cvat_attributes_recognition'
    annotation_types = (ClassificationAnnotation, )
    topology_types = (ImageClassification, )

    @classmethod
    def parameters(cls):
        parameters = super().parameters()
        parameters.update({
            'label': StringField(description='specific label for attribute collection'),
            'images_dir': PathField(
                is_directory=True, optional=True,
                description='path to dataset images, used only for content existence check'
            )
        })
        return parameters

    def configure(self):
        super().configure()
        self.label = self.get_value_from_config('label')
        self.images_dir = self.get_value_from_config('images_dir') or self.annotation_file.parent

    def convert(self, check_content=False, progress_callback=None, progress_interval=100, **kwargs):
        annotation = read_xml(self.annotation_file)
        meta = annotation.find('meta')
        size = int(meta.find('size').text)
        label = [label for label in meta.iter('label') if label.find('name').text == self.label]
        if not label:
            raise ConfigError('{} does not present in annotation')
        label = label[0]
        attribute_values_mapping = {}
        for attribute in label.iter('attribute'):
            label_to_id = {
                label: idx for idx, label in enumerate(attribute.find('values').text.split('\n'))
            }
            attribute_values_mapping[attribute.find('name').text] = label_to_id

        annotations = []
        content_errors = None if not check_content else []
        for image_id, image in enumerate(annotation.iter('image')):
            identifier = image.attrib['name'].split('/')[-1]
            if check_content:
                if not check_file_existence(self.images_dir / identifier):
                    content_errors.append('{}: does not exist'.format(self.images_dir / identifier))
            for bbox in image:
                if 'label' not in bbox.attrib.keys() or bbox.attrib['label'] != self.label:
                    continue
                annotation_dict = {}
                bbox_rect = [
                    float(bbox.attrib['xtl']), float(bbox.attrib['ytl']),
                    float(bbox.attrib['xbr']), float(bbox.attrib['ybr'])
                ]
                for attribute in bbox.iter('attribute'):
                    attribute_name = attribute.attrib['name']
                    attribute_label = attribute_values_mapping[attribute_name][attribute.text]
                    attribute_annotation = ClassificationAnnotation(identifier, attribute_label)
                    attribute_annotation.metadata['rect'] = bbox_rect
                    annotation_dict[attribute_name] = attribute_annotation
                if len(annotation_dict) == 1:
                    annotations.append(next(iter(annotation_dict.values())))
                else:
                    annotations.append(ContainerAnnotation(annotation_dict))
                if progress_callback is not None and image_id % progress_interval == 0:
                    progress_callback(image_id * 100 / size)

        return ConverterReturn(annotations, self.generate_meta(attribute_values_mapping), content_errors)

    @staticmethod
    def generate_meta(attribute_values_mapping):
        if len(attribute_values_mapping) == 1:
            reversed_label_map = next(iter(attribute_values_mapping.values()))
            return {'label_map': {value: key for key, value in reversed_label_map.items()}}

        meta = {}
        for key, reversed_label_map in attribute_values_mapping.items():
            meta['{}_label_map'.format(key)] = {value: key for key, value in reversed_label_map.items()}

        return meta