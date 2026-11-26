"""Bound decoding work, discard metadata, and give every stored image a fresh name."""
from io import BytesIO
from uuid import uuid4

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers


class SafeImageField(serializers.ImageField):
    def to_internal_value(self, data):
        if not hasattr(data,'size') or data.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Choose a JPEG or PNG no larger than 5 MB.')
        try:
            with Image.open(data,formats=('JPEG','PNG')) as src:
                if src.format not in ('JPEG','PNG') or src.width * src.height > 12_000_000 or getattr(src,'n_frames',1) > 1:
                    raise serializers.ValidationError('Only still JPEG/PNG images up to 12 megapixels are accepted.')
                src.load()
                # convert() copies src.info, and the JPEG encoder consults it for
                # comments/profiles. Copy only pixels into a fresh encoding surface.
                with src.convert('RGB') as pixels:
                    pixels.thumbnail((1800,1800))
                    with Image.new('RGB',pixels.size) as clean:
                        clean.paste(pixels)
                        out = BytesIO()
                        clean.save(out, format='JPEG', quality=85)
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise serializers.ValidationError('Unreadable image.') from exc
        return ContentFile(out.getvalue(), name=f'{uuid4().hex}.jpg')

    def to_representation(self,value):
        return value.url if value else None
