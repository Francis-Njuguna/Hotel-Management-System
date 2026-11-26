from io import BytesIO
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image, PngImagePlugin
from rest_framework.test import APITestCase

from .models import MenuItem


class MenuTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cook = get_user_model().objects.create_user("synthetic-menu-operator")
        cls.cook.groups.add(Group.objects.get(name="Restaurant Staff"))
        cls.desk = get_user_model().objects.create_user("synthetic-menu-outsider")
        cls.desk.groups.add(Group.objects.get(name="Receptionist"))

    def setUp(self):
        self.client.force_authenticate(self.cook)
        self.item = {"name": "Synthetic tea", "category": "Drinks", "price": "3.40"}

    def test_multipart_image_is_reencoded_and_served_only_with_catalog_grant(self):
        png = BytesIO()
        tags = PngImagePlugin.PngInfo()
        tags.add_text("Comment", "synthetic-metadata-to-remove")
        Image.new("RGB", (9, 7), "green").save(png, format="PNG", pnginfo=tags)
        upload = SimpleUploadedFile("original-fixture.png", png.getvalue(), content_type="image/png")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            created = self.client.post("/api/v1/menu-items/", {**self.item, "image": upload}, format="multipart", secure=True)
            self.assertEqual(created.status_code, 201, created.content)
            self.assertEqual(created.json()["price"], "3.40")
            key = MenuItem.objects.get().image.name
            self.assertRegex(key, r"^menu/[a-f0-9]{32}\.jpg$")
            path = urlsplit(created.json()["image"]).path
            self.assertEqual(path, f"/api/v1/media/{key}")
            fetched = self.client.get(path, secure=True)
            self.assertEqual(fetched.status_code, 200)
            # Django's test client closes the response at the end of iteration.
            # Closing it twice also sends request_finished twice inside TestCase's transaction.
            clean = b"".join(fetched.streaming_content)
            self.assertTrue(fetched.closed)
            self.assertNotIn(b"synthetic-metadata-to-remove", clean)
            with Image.open(BytesIO(clean)) as image:
                self.assertEqual((image.format, image.size), ("JPEG", (9, 7)))
            self.client.force_authenticate(self.desk)
            self.assertIn(self.client.get(path, secure=True).status_code, (403, 404))
            self.assertEqual(self.client.get("/api/v1/menu-items/", secure=True).status_code, 403)

    def test_reject_unreadable_image_and_invalid_money_without_catalog_writes(self):
        fake = SimpleUploadedFile("not-an-image.png", b"plain synthetic fixture", content_type="image/png")
        response = self.client.post("/api/v1/menu-items/", {**self.item, "image": fake}, format="multipart", secure=True)
        self.assertEqual(response.status_code, 400, response.content)
        for value in ("-1.00", "0.001", "NaN", 1.25):
            with self.subTest(price=value):
                response = self.client.post("/api/v1/menu-items/", {**self.item, "price": value}, format="json", secure=True)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(MenuItem.objects.exists())
