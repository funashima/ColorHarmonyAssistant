#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import math
import time
import pathlib
import requests

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal, pyqtSlot

UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"


class UnsplashDownloader(QtCore.QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    # 画像枚数用
    progress_max = pyqtSignal(int)
    progress_value = pyqtSignal(int)
    # ページ（検索リクエスト）用
    page_max = pyqtSignal(int)
    page_value = pyqtSignal(int)

    def __init__(
        self,
        access_key: str,
        jobs: list,
        output_dir: str,
        limit_per_hour: int = 50,
        orientation: str = "",
        color: str = "",
        order_by: str = "relevant",
        content_filter: str = "low",
        auto_retry: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.access_key = access_key.strip()
        self.jobs = jobs  # [{ "keyword": str, "count": int }, ...]
        self.output_dir = pathlib.Path(output_dir)
        self.limit_per_hour = limit_per_hour
        self.orientation = orientation.strip()
        self.color = color.strip()
        self.order_by = order_by.strip() or "relevant"
        self.content_filter = content_filter.strip() or "low"
        self.auto_retry = auto_retry
        self._stop_flag = False

    @pyqtSlot()
    def run(self):
        try:
            if not self.jobs:
                self.error.emit("キーワード行がありません。")
                self.finished.emit()
                return

            # Access Key
            if not self.access_key:
                env_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
                if not env_key:
                    self.error.emit("Unsplash Access Key が指定されていません。")
                    self.finished.emit()
                    return
                self.access_key = env_key

            self.output_dir.mkdir(parents=True, exist_ok=True)

            # 全ジョブの合計枚数
            total_images = sum(job["count"] for job in self.jobs)
            if total_images <= 0:
                self.error.emit("取得枚数が0です。キーワード行を確認してください。")
                self.finished.emit()
                return

            # 進捗バー（画像）の最大値
            self.progress_max.emit(total_images)
            self.progress_value.emit(0)

            # 自前の安全枠
            safe_limit = max(1, int(self.limit_per_hour * 0.9))
            interval_sec = 3600.0 / safe_limit

            self.progress.emit(
                f"1時間あたりリクエスト上限={self.limit_per_hour}, "
                f"安全枠={safe_limit}, リクエスト間隔≈{interval_sec:.1f}秒"
            )

            headers = {
                "Accept-Version": "v1",
                "Authorization": f"Client-ID {self.access_key}",
            }

            per_page = 30
            total_downloaded = 0
            request_count = 0

            for job_index, job in enumerate(self.jobs, start=1):
                if self._stop_flag:
                    self.progress.emit("停止要求を受けたため中断しました。")
                    break

                keyword = job["keyword"]
                target_count = job["count"]
                if target_count <= 0:
                    continue

                self.progress.emit(
                    f"[ジョブ {job_index}/{len(self.jobs)}] "
                    f"キーワード '{keyword}' を処理します（{target_count}枚）"
                )

                job_downloaded = 0
                pages_needed = math.ceil(target_count / per_page) if target_count > 0 else 0
                if pages_needed <= 0:
                    continue

                # ページ進捗バー（ジョブごとにリセット）
                self.page_max.emit(pages_needed)
                self.page_value.emit(0)

                for page in range(1, pages_needed + 1):
                    if self._stop_flag:
                        self.progress.emit("停止要求を受けたため中断しました。")
                        break

                    # ---- 1ページ分のリクエスト（レート制限対応付き） ----
                    while True:
                        if self._stop_flag:
                            break

                        params = {
                            "query": keyword,
                            "page": page,
                            "per_page": per_page,
                            "order_by": self.order_by,
                            "content_filter": self.content_filter,
                        }
                        if self.orientation:
                            params["orientation"] = self.orientation
                        if self.color:
                            params["color"] = self.color

                        self.progress.emit(
                            f"[ジョブ {job_index}/{len(self.jobs)}]"
                            f" [{page}/{pages_needed}] 検索中… (request {request_count + 1})"
                        )

                        try:
                            resp = requests.get(
                                UNSPLASH_SEARCH_URL,
                                headers=headers,
                                params=params,
                                timeout=15,
                            )
                        except Exception as e:
                            self.error.emit(f"検索リクエストエラー: {e}")
                            self.finished.emit()
                            return

                        request_count += 1

                        # 正常
                        if resp.status_code == 200:
                            break

                        # レート制限の可能性
                        if resp.status_code in (403, 429):
                            remaining = resp.headers.get("X-Ratelimit-Remaining", None)
                            reset_ts = resp.headers.get("X-Ratelimit-Reset", None)
                            self.progress.emit(
                                f"Rate limit debug: remaining={remaining}, reset={reset_ts}"
                            )

                            try:
                                remaining_int = (
                                    int(remaining) if remaining is not None else None
                                )
                            except ValueError:
                                remaining_int = None

                            if self.auto_retry:
                                wait_sec = None

                                # 1) 正常に reset 時刻が取れた場合
                                if (
                                    remaining_int == 0
                                    and reset_ts
                                    and reset_ts.isdigit()
                                ):
                                    now = int(time.time())
                                    reset_epoch = int(reset_ts)
                                    wait_sec = max(0, reset_epoch - now)

                                # 2) ヘッダが微妙でも "Rate Limit Exceeded" と書いてあれば1時間待ち
                                if wait_sec is None and "Rate Limit Exceeded" in resp.text:
                                    wait_sec = 3600

                                if wait_sec is not None:
                                    wait_min = wait_sec // 60
                                    self.progress.emit(
                                        "Unsplash のレート制限に達しました。"
                                        f"約 {wait_min} 分待ってから自動再試行します…"
                                    )
                                    for _ in range(wait_sec):
                                        if self._stop_flag:
                                            self.progress.emit(
                                                "停止要求を受けたため待機を中断しました。"
                                            )
                                            self.finished.emit()
                                            return
                                        time.sleep(1)

                                    self.progress.emit(
                                        "レート制限の待機が終了したので再試行します。"
                                    )
                                    # 同じページを再リクエスト
                                    continue

                            # 自動再試行できない
                            self.error.emit(
                                "Unsplash のレート制限に達しました。"
                                "自動再試行は無効か、待機時間を安全に計算できませんでした。"
                                f" (HTTP {resp.status_code}: {resp.text[:200]})"
                            )
                            self.finished.emit()
                            return

                        # その他のエラー
                        self.error.emit(
                            f"HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        self.finished.emit()
                        return

                    if self._stop_flag:
                        break

                    data = resp.json()
                    results = data.get("results", [])

                    if not results:
                        self.progress.emit(
                            f"キーワード '{keyword}' ではこれ以上の結果がありません。"
                        )
                        break

                    for photo in results:
                        if self._stop_flag:
                            self.progress.emit("停止要求を受けたため中断しました。")
                            break

                        if job_downloaded >= target_count:
                            break

                        photo_id = photo.get("id", "unknown")
                        links = photo.get("links", {})
                        urls = photo.get("urls", {})

                        # download_location 経由でダウンロードを記録
                        download_url = None
                        dl_loc = links.get("download_location")

                        if dl_loc:
                            try:
                                track_params = {"client_id": self.access_key}
                                track_resp = requests.get(
                                    dl_loc, params=track_params, timeout=10
                                )
                                if track_resp.status_code == 200:
                                    try:
                                        dl_json = track_resp.json()
                                        download_url = dl_json.get("url")
                                    except Exception as je:
                                        self.progress.emit(
                                            f"download_location JSON解析失敗({photo_id}): {je}"
                                        )
                                else:
                                    self.progress.emit(
                                        "download_location "
                                        f"(使用状況トラッキング) 呼び出し失敗({photo_id}): "
                                        f"HTTP {track_resp.status_code}"
                                    )
                            except Exception as e:
                                self.progress.emit(
                                    f"download_location アクセスエラー({photo_id}): {e}"
                                )

                        # フォールバック: urls.full → urls.regular
                        if not download_url:
                            download_url = urls.get("full") or urls.get("regular")

                        if not download_url:
                            self.progress.emit(
                                f"ダウンロードURLが見つからないためスキップ: {photo_id}"
                            )
                            continue

                        # ファイル名: キーワード_写真ID.jpg
                        safe_keyword = keyword.replace(" ", "_")
                        file_path = self.output_dir / f"{safe_keyword}_{photo_id}.jpg"

                        try:
                            img_resp = requests.get(
                                download_url, stream=True, timeout=30
                            )
                            if img_resp.status_code == 200:
                                with open(file_path, "wb") as f:
                                    for chunk in img_resp.iter_content(8192):
                                        if chunk:
                                            f.write(chunk)
                                job_downloaded += 1
                                total_downloaded += 1
                                self.progress_value.emit(total_downloaded)
                                self.progress.emit(
                                    f"[{total_downloaded}/{total_images}] "
                                    f"保存: {file_path.name}"
                                )
                            else:
                                self.progress.emit(
                                    f"画像取得失敗({img_resp.status_code}): {photo_id}"
                                )
                        except Exception as e:
                            self.progress.emit(f"画像取得エラー({photo_id}): {e}")

                    # ページ進捗更新
                    self.page_value.emit(page)

                    if job_downloaded >= target_count:
                        self.progress.emit(
                            f"キーワード '{keyword}' の指定枚数 {target_count} 枚のダウンロードが完了しました。"
                        )
                        break

                    # インターバル（安全マージン）
                    if interval_sec >= 1.0 and page < pages_needed:
                        for _ in range(int(interval_sec)):
                            if self._stop_flag:
                                self.progress.emit("停止要求を受けたため待機を中断しました。")
                                break
                            time.sleep(1)
                        if self._stop_flag:
                            break

                if self._stop_flag:
                    break

            if not self._stop_flag:
                self.progress.emit("すべてのキーワードの処理が完了しました。")

            self.finished.emit()

        except Exception as e:
            self.error.emit(f"予期しないエラー: {e}")
            self.finished.emit()

    def stop(self):
        self._stop_flag = True


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unsplash Image Downloader")
        self.resize(900, 720)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        form_layout = QtWidgets.QFormLayout()

        # Access Key + ファイル読込ボタン
        api_layout = QtWidgets.QHBoxLayout()
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText(
            "Unsplash Access Key（空なら UNSPLASH_ACCESS_KEY を使用）"
        )
        self.api_key_file_btn = QtWidgets.QPushButton("ファイルから読込…")
        self.api_key_file_btn.clicked.connect(self.load_access_key_from_file)
        api_layout.addWidget(self.api_key_edit)
        api_layout.addWidget(self.api_key_file_btn)
        form_layout.addRow("Access Key:", api_layout)

        # キーワード表 + 行追加/削除ボタン
        self.keyword_table = QtWidgets.QTableWidget(0, 2)
        self.keyword_table.setHorizontalHeaderLabels(["キーワード", "枚数"])
        header = self.keyword_table.horizontalHeader()
        header.setStretchLastSection(True)
        self.keyword_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

        kw_btn_layout = QtWidgets.QHBoxLayout()
        self.add_row_btn = QtWidgets.QPushButton("行追加")
        self.del_row_btn = QtWidgets.QPushButton("選択行削除")
        self.add_row_btn.clicked.connect(self.add_keyword_row)
        self.del_row_btn.clicked.connect(self.remove_selected_rows)
        kw_btn_layout.addWidget(self.add_row_btn)
        kw_btn_layout.addWidget(self.del_row_btn)

        kw_layout = QtWidgets.QVBoxLayout()
        kw_layout.addWidget(self.keyword_table)
        kw_layout.addLayout(kw_btn_layout)

        form_layout.addRow("キーワード一覧:", kw_layout)

        # デフォルトで1行追加
        self.add_keyword_row()

        # 1時間あたりのAPI上限 (requests/hour)
        self.limit_spin = QtWidgets.QSpinBox()
        self.limit_spin.setRange(1, 5000)
        self.limit_spin.setValue(50)
        self.limit_spin.setSuffix(" req / hour")
        form_layout.addRow("1時間あたりのAPI上限:", self.limit_spin)

        # orientation 指定
        self.orientation_combo = QtWidgets.QComboBox()
        self.orientation_combo.addItem("指定なし (default)", "")
        self.orientation_combo.addItem("横長 (landscape)", "landscape")
        self.orientation_combo.addItem("縦長 (portrait)", "portrait")
        self.orientation_combo.addItem("正方形寄り (squarish)", "squarish")
        form_layout.addRow("向き (orientation):", self.orientation_combo)

        # color 指定
        self.color_combo = QtWidgets.QComboBox()
        self.color_combo.addItem("指定なし (default)", "")
        self.color_combo.addItem("モノクロ (black_and_white)", "black_and_white")
        self.color_combo.addItem("黒 (black)", "black")
        self.color_combo.addItem("白 (white)", "white")
        self.color_combo.addItem("黄 (yellow)", "yellow")
        self.color_combo.addItem("オレンジ (orange)", "orange")
        self.color_combo.addItem("赤 (red)", "red")
        self.color_combo.addItem("紫 (purple)", "purple")
        self.color_combo.addItem("マゼンタ (magenta)", "magenta")
        self.color_combo.addItem("緑 (green)", "green")
        self.color_combo.addItem("シアン (teal)", "teal")
        self.color_combo.addItem("青 (blue)", "blue")
        form_layout.addRow("色 (color):", self.color_combo)

        # order_by
        self.order_by_combo = QtWidgets.QComboBox()
        self.order_by_combo.addItem("関連順 (relevant)", "relevant")
        self.order_by_combo.addItem("新着順 (latest)", "latest")
        form_layout.addRow("並び順 (order_by):", self.order_by_combo)

        # content_filter
        self.content_filter_combo = QtWidgets.QComboBox()
        self.content_filter_combo.addItem("標準 (low)", "low")
        self.content_filter_combo.addItem("より厳しく (high)", "high")
        form_layout.addRow("コンテンツフィルタ:", self.content_filter_combo)

        # 自動再試行チェックボックス
        self.auto_retry_checkbox = QtWidgets.QCheckBox(
            "レート制限時に自動で待機して再試行する"
        )
        self.auto_retry_checkbox.setChecked(True)
        form_layout.addRow("", self.auto_retry_checkbox)

        # 保存フォルダ
        out_layout = QtWidgets.QHBoxLayout()
        self.output_edit = QtWidgets.QLineEdit()
        self.output_edit.setText(str(pathlib.Path.cwd() / "unsplash_images"))
        browse_btn = QtWidgets.QPushButton("参照…")
        browse_btn.clicked.connect(self.browse_output_dir)
        out_layout.addWidget(self.output_edit)
        out_layout.addWidget(browse_btn)
        form_layout.addRow("保存フォルダ:", out_layout)

        # ボタン
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("開始")
        self.stop_btn = QtWidgets.QPushButton("停止")
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        form_layout.addRow(btn_layout)

        # 進捗バー（画像枚数）
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(0)
        form_layout.addRow("画像進捗:", self.progress_bar)

        # 進捗バー（ページ／リクエスト）
        self.page_progress_bar = QtWidgets.QProgressBar()
        self.page_progress_bar.setMinimum(0)
        self.page_progress_bar.setMaximum(0)
        form_layout.addRow("ページ進捗:", self.page_progress_bar)

        # ログ
        self.log_edit = QtWidgets.QTextEdit()
        self.log_edit.setReadOnly(True)
        form_layout.addRow("ログ:", self.log_edit)

        central.setLayout(form_layout)

        self.start_btn.clicked.connect(self.start_download)
        self.stop_btn.clicked.connect(self.stop_download)

        self.thread: QtCore.QThread | None = None
        self.worker: UnsplashDownloader | None = None

    # --- キーワード表操作 ---

    def add_keyword_row(self):
        row = self.keyword_table.rowCount()
        self.keyword_table.insertRow(row)
        # デフォルト値: 空キーワード / 50枚
        self.keyword_table.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        self.keyword_table.setItem(row, 1, QtWidgets.QTableWidgetItem("50"))

    def remove_selected_rows(self):
        rows = sorted(
            {idx.row() for idx in self.keyword_table.selectedIndexes()},
            reverse=True,
        )
        for r in rows:
            self.keyword_table.removeRow(r)
        if self.keyword_table.rowCount() == 0:
            self.add_keyword_row()

    # --- UI helper methods ---

    def load_access_key_from_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "accesskey.txt を選択",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                line = f.readline().strip()
            if not line:
                QtWidgets.QMessageBox.warning(
                    self, "エラー", "ファイルに有効なAccess Keyが見つかりません。"
                )
                return
            self.api_key_edit.setText(line)
            self.append_log(f"Access Key をファイルから読み込みました: {file_path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "エラー", f"Access Key ファイルの読み込みに失敗しました:\n{e}"
            )

    def browse_output_dir(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "保存フォルダを選択"
        )
        if directory:
            self.output_edit.setText(directory)

    def append_log(self, text: str):
        self.log_edit.append(text)

    def set_controls_enabled(self, enabled: bool):
        self.api_key_edit.setEnabled(enabled)
        self.api_key_file_btn.setEnabled(enabled)
        self.keyword_table.setEnabled(enabled)
        self.add_row_btn.setEnabled(enabled)
        self.del_row_btn.setEnabled(enabled)
        self.limit_spin.setEnabled(enabled)
        self.output_edit.setEnabled(enabled)
        self.orientation_combo.setEnabled(enabled)
        self.color_combo.setEnabled(enabled)
        self.order_by_combo.setEnabled(enabled)
        self.content_filter_combo.setEnabled(enabled)
        self.auto_retry_checkbox.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)

    # --- 進捗バー更新用スロット ---

    def set_progress_max(self, maximum: int):
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(0)

    def set_progress_value(self, value: int):
        self.progress_bar.setValue(value)

    def set_page_max(self, maximum: int):
        self.page_progress_bar.setMinimum(0)
        self.page_progress_bar.setMaximum(maximum)
        self.page_progress_bar.setValue(0)

    def set_page_value(self, value: int):
        self.page_progress_bar.setValue(value)

    # --- Worker control ---

    def start_download(self):
        out_dir = self.output_edit.text().strip()
        if not out_dir:
            QtWidgets.QMessageBox.warning(self, "エラー", "保存フォルダを指定してください。")
            return

        # キーワード行からジョブを作成
        jobs = []
        for row in range(self.keyword_table.rowCount()):
            kw_item = self.keyword_table.item(row, 0)
            cnt_item = self.keyword_table.item(row, 1)
            keyword = kw_item.text().strip() if kw_item else ""
            count_str = cnt_item.text().strip() if cnt_item else ""

            if not keyword:
                continue  # 空行は無視

            if not count_str.isdigit():
                QtWidgets.QMessageBox.warning(
                    self,
                    "エラー",
                    f"{row + 1}行目の枚数が不正です: '{count_str}'",
                )
                return

            count = int(count_str)
            if count <= 0:
                continue

            jobs.append({"keyword": keyword, "count": count})

        if not jobs:
            QtWidgets.QMessageBox.warning(
                self, "エラー", "有効なキーワード行がありません。"
            )
            return

        access_key = self.api_key_edit.text()
        limit_per_hour = self.limit_spin.value()
        orientation = self.orientation_combo.currentData()
        color = self.color_combo.currentData()
        order_by = self.order_by_combo.currentData()
        content_filter = self.content_filter_combo.currentData()
        auto_retry = self.auto_retry_checkbox.isChecked()

        self.log_edit.clear()
        self.append_log("ダウンロードを開始します…")

        total_images = sum(job["count"] for job in jobs)
        self.set_progress_max(total_images)
        self.set_page_max(0)

        self.set_controls_enabled(False)
        self.stop_btn.setEnabled(True)

        # 既存スレッドが残っていれば片付ける
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

        self.thread = QtCore.QThread(self)
        self.worker = UnsplashDownloader(
            access_key=access_key,
            jobs=jobs,
            output_dir=out_dir,
            limit_per_hour=limit_per_hour,
            orientation=orientation,
            color=color,
            order_by=order_by,
            content_filter=content_filter,
            auto_retry=auto_retry,
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.append_log)
        self.worker.error.connect(self.on_worker_error)
        self.worker.finished.connect(self.on_worker_finished)

        self.worker.progress_max.connect(self.set_progress_max)
        self.worker.progress_value.connect(self.set_progress_value)
        self.worker.page_max.connect(self.set_page_max)
        self.worker.page_value.connect(self.set_page_value)

        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.worker.deleteLater)

        self.thread.start()

    def stop_download(self):
        if self.worker is not None:
            self.worker.stop()
            self.append_log("停止要求を送信しました。")
        self.stop_btn.setEnabled(False)

    def on_worker_error(self, msg: str):
        self.append_log(f"[ERROR] {msg}")
        QtWidgets.QMessageBox.critical(self, "エラー", msg)

    def on_worker_finished(self):
        self.append_log("処理が完了しました。")
        self.set_controls_enabled(True)
        self.stop_btn.setEnabled(False)

        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

        self.worker = None
        self.thread = None

    # ウィンドウを閉じるときも安全にスレッド停止
    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        event.accept()


def main():
    import sys

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
