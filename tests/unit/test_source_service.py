import io
import json
import os
import shutil
import unittest
import zipfile
from unittest import mock

from src.core.storage.file_store import FileStore
from src.modules.runner.source_service import SourceService

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_source_service")


class FakeUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self.file = io.BytesIO(data)


class SourceServiceBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(BASE, exist_ok=True)
        self.store = FileStore(base_dir=BASE)
        self.service = SourceService(self.store)

    def tearDown(self):
        if os.path.isdir(BASE):
            shutil.rmtree(BASE, ignore_errors=True)

    def make_folder(self, name: str, files: dict) -> str:
        folder = os.path.join(BASE, "chosen", name)
        for rel, content in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        return folder


class TestPathSources(SourceServiceBase):
    def test_from_path_registers_and_prepares_script_mode(self):
        folder = self.make_folder("app", {"main.py": "print('hi')\n"})
        info = self.service.from_path(folder)
        self.assertTrue(info.source_id.startswith("SRC-"))
        self.assertEqual(info.kind, "path")

        prepare = self.service.prepare(info.source_id)
        self.assertEqual(prepare.mode, "script")
        self.assertEqual(prepare.suggested_command, ["{python}", "main.py"])
        self.assertEqual(prepare.suggested_feature, "app")

    def test_same_path_is_registered_once(self):
        folder = self.make_folder("app", {"main.py": "print('hi')\n"})
        first = self.service.from_path(folder)
        second = self.service.from_path(folder, "ten_moi")
        self.assertEqual(first.source_id, second.source_id)
        self.assertEqual(len(self.service.list_sources()), 1)

    def test_missing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.service.from_path(os.path.join(BASE, "khong_ton_tai"))

    def test_recorded_mode_when_runs_file_exists(self):
        folder = self.make_folder(
            "logs", {"runs.json": json.dumps({"runs": [{"run_id": "a", "latency_ms": 12}]})}
        )
        prepare = self.service.prepare(self.service.from_path(folder).source_id)
        self.assertEqual(prepare.mode, "recorded")
        self.assertEqual(prepare.runs_available, 1)
        self.assertIsNone(prepare.suggested_command)

    def test_empty_mode_when_no_script_and_no_runs(self):
        folder = self.make_folder("data_only", {"notes.txt": "chỉ có text"})
        prepare = self.service.prepare(self.service.from_path(folder).source_id)
        self.assertEqual(prepare.mode, "empty")
        self.assertIsNone(prepare.suggested_command)
        self.assertEqual(prepare.scripts, [])

    def test_feature_name_is_sanitized(self):
        self.assertEqual(SourceService.feature_name("Chatbot NCKH v2!"), "Chatbot_NCKH_v2")

    def test_server_like_script_gets_warning_note(self):
        folder = self.make_folder(
            "web",
            {
                "app.py": "from flask import Flask\napp = Flask(__name__)\n"
                           "if __name__ == '__main__':\n    app.run(debug=True)\n",
                "batch.py": "print('STEP work 1.0')\n",
            },
        )
        prepare = self.service.prepare(self.service.from_path(folder).source_id)
        self.assertTrue(any("app.py" in n and "web server" in n for n in prepare.notes), prepare.notes)
        self.assertTrue(any("bỏ qua script web server" in n for n in prepare.notes), prepare.notes)
        # web server không được làm lệnh gợi ý — ưu tiên script batch
        self.assertEqual(prepare.suggested_command, ["{python}", "batch.py"])

    def test_batch_script_has_no_warning(self):
        folder = self.make_folder("batch_only", {"run_it.py": "print('STEP a 1.0')\n"})
        prepare = self.service.prepare(self.service.from_path(folder).source_id)
        self.assertEqual(prepare.notes, [])

    def test_unknown_source_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.service.prepare("SRC-9999")


class TestSafeRel(unittest.TestCase):
    def test_normal_paths_pass(self):
        self.assertEqual(SourceService.safe_rel("a/b.py"), "a/b.py")
        self.assertEqual(SourceService.safe_rel("a\\b.py"), "a/b.py")
        self.assertEqual(SourceService.safe_rel("./a.py"), "a.py")

    def test_traversal_and_absolute_are_rejected(self):
        for bad in ("../evil.py", "a/../../evil.py", "/etc/passwd", "C:\\evil.py", "", "///"):
            with self.assertRaises(ValueError, msg=bad):
                SourceService.safe_rel(bad)


class TestUploadSources(SourceServiceBase):
    def test_upload_files_keeps_folder_structure(self):
        files = [FakeUpload("main.py", b"print('hi')"), FakeUpload("data/a.txt", b"abc")]
        info = self.service.from_upload(files, ["main.py", "data/a.txt"], "bai_test")

        self.assertEqual(info.kind, "upload")
        self.assertTrue(os.path.exists(os.path.join(info.folder, "main.py")))
        self.assertTrue(os.path.exists(os.path.join(info.folder, "data", "a.txt")))
        self.assertEqual(info.name, "bai_test")

        prepare = self.service.prepare(info.source_id)
        self.assertEqual(prepare.mode, "script")
        self.assertEqual(prepare.suggested_command, ["{python}", "main.py"])

    def test_upload_zip_is_extracted(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("runs.json", json.dumps({"runs": [{"run_id": "a", "latency_ms": 5}]}))
            archive.writestr("pkg/note.txt", "x")
        info = self.service.from_upload([FakeUpload("bundle.zip", buffer.getvalue())])

        self.assertTrue(os.path.exists(os.path.join(info.folder, "pkg", "note.txt")))
        self.assertEqual(self.service.prepare(info.source_id).mode, "recorded")

    def test_traversal_path_is_rejected_and_folder_removed(self):
        with self.assertRaises(ValueError):
            self.service.from_upload([FakeUpload("evil.py", b"x")], ["../evil.py"])
        uploads = os.path.join(BASE, "uploads")
        self.assertEqual(os.listdir(uploads) if os.path.isdir(uploads) else [], [])

    def test_zip_with_traversal_member_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.py", b"boom")
        with self.assertRaises(ValueError):
            self.service.from_upload([FakeUpload("bad.zip", buffer.getvalue())])
        uploads = os.path.join(BASE, "uploads")
        self.assertEqual(os.listdir(uploads) if os.path.isdir(uploads) else [], [])

    def test_empty_upload_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.from_upload([])

    def test_size_limit_is_enforced(self):
        with mock.patch("src.modules.runner.source_service.MAX_TOTAL_BYTES", 10):
            with self.assertRaises(ValueError):
                self.service.from_upload([FakeUpload("big.txt", b"x" * 50)])
        uploads = os.path.join(BASE, "uploads")
        self.assertEqual(os.listdir(uploads) if os.path.isdir(uploads) else [], [])


if __name__ == "__main__":
    unittest.main()
