# Interior Color Harmony Assistant

**PyQt6 デスクトップアプリ**で室内写真からカラーパレットを抽出し、
色彩調和スコア（補色・類似色・単色・スプリット補色・トライアド）や HSV 統計を特徴量化。
スタイルごと（e.g., *Japanese*, *Nordic*, *Ethnic* …）に **RandomForest / LightGBM** で学習し、
評価対象画像の「スタイルらしさ」と**何が足りないか**をレポート＋グラフで提示します。
付属の **Style JSON Editor** で `style.json`（学習用フォルダ定義）をGUI編集できます。

> 日本語 UI／レポート。教育用途向けに丁寧なコメント入りコード構成。

---

## 主な機能

* 画像から **KMeans** によるカラーパレット抽出（自動 k も可、サンプリング上限）
* 5 つの色彩調和メトリクス + 加重総合スコア
* HSV 統計（支配色/平均色の H・S・V、支配面積比など）
* **重み自動学習**（LogisticRegression による各調和スコアの寄与推定）
* **学習**：スタイル別に正例/負例で 2 クラス分類（RandomForest / LightGBM 切替）
* **評価**：画像ごとの「スタイルらしさ」＋不足項目のテキスト解説
* ギャップ棒グラフ（**+ 赤 / − 青**）、プレビュー（ズーム/原寸/フィット/外部ポップアウト）
* **抽出パレットの可視化**（色チップ＋比率表示）
* **提案サマリー**：目標スタイルに近づけるための実践的ヒントを自動生成
* **Style JSON Editor**：style.json の読み込み/保存、検証、複製、順序入替、画像枚数カウント

---

## デモ（スクリーンショット）

> `docs/` に画像を置き、下のパスを差し替えてください。

* メインアプリ（詳細タブ / レポート＋プレビュー＋ギャップ図）
  ![Main](docs/main_detail.png)

* Style JSON Editor（一覧 + 右ペイン編集）
  ![Editor](docs/style_editor.png)

---

## インストール

### 1) 環境

* OS: Linux / Windows / macOS（Ubuntu 推奨）
* Python: 3.10+ 推奨
* （任意）LightGBM を使う場合は OS 側の依存が増えます。難しい場合は RandomForest を使ってください。

### 2) 依存パッケージ

```bash
python -m venv .venv
source .venv/bin/activate   # Windowsは .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

`requirements.txt`（抜粋）

```
PyQt6>=6.5
numpy>=1.24
scipy>=1.10
pandas>=2.0
scikit-learn>=1.3
kneed>=0.8.5
lightgbm>=4.0    # 任意
opencv-python-headless>=4.8
matplotlib>=3.7
```

> OpenCV は GUI を使わないので `opencv-python-headless` を採用しています。
> OpenCV のウィンドウが必要なら `opencv-python` に置換してください。

---

## プロジェクト構成（例）

```
.
├── ColorHarmonyAssistant            # メインGUIアプリ
├── StyleJsonEditor                  # style.json編集GUI
├── requirements.txt
├── style.json                       # スタイル定義（後述）
├── dataset/
│   ├── typical_rooms/
│   │   ├── japanese/ ...           # 正例(positive)
│   │   └── nordic/   ...
│   ├── untypical_rooms/
│   │   └── no_style/ ...           # 負例(negative)
│   └── evaluated_rooms/ ...        # 評価対象（任意名OK）
└── docs/
    ├── main_detail.png
    └── style_editor.png
```

---

## 使い方（メインアプリ）

```bash
python ColorHarmonyAssistant.py
```

1. 左ペイン「**style.json を読み込む**」からスタイル定義を読み込み
2. 「**モデル学習（style.json 全スタイル）**」を実行

   * 必要に応じて「抽出/調和」タブで **KMeans 色数**、**自動 k**、**重み自動学習**を調整
   * 「モデル」タブで RandomForest/LightGBM とハイパーパラメータを選択
3. 「**評価フォルダを選択（evaluated_rooms）**」→「**評価を実行**」
4. 右ペイン「**サマリー**」で各スタイルの *likeness* を俯瞰
5. 「**詳細レポート**」で画像を選ぶと

   * テキスト解説（不足/過剰のポイント）
   * ギャップ棒グラフ（調和・色統計）
   * 画像プレビュー（ズーム/原寸/フィット/外部表示）
   * 抽出パレット（色チップ + 比率）
   * **目標スタイルに近づける提案サマリー**

> グラフサイズは 75%（4.5×2.25inch）。スプリッタでレイアウトの高さを自由に調整できます。

---

## style.json の書式

**dict 形式（推奨・デフォルト保存）**

```json
{
  "japanese_style": {
    "positive": "dataset/typical_rooms/japanese",
    "negative": "dataset/untypical_rooms/no_style"
  },
  "nordic_style": {
    "positive": "dataset/typical_rooms/nordic",
    "negative": "dataset/untypical_rooms/no_style"
  }
}
```

**list 形式（読み書き対応）**

```json
[
  {"name": "japanese_style", "positive": "dataset/typical_rooms/japanese", "negative": "dataset/untypical_rooms/no_style"},
  {"name": "nordic_style",   "positive": "dataset/typical_rooms/nordic",   "negative": "dataset/untypical_rooms/no_style"}
]
```

* `positive`：そのスタイルの**正例**ディレクトリ
* `negative`：**負例**ディレクトリ（「no_style」や他スタイルのミックスでも可）
* パスは相対/絶対どちらでも可。
* 画像拡張子：`.jpg/.jpeg/.png/.bmp/.webp`

---

## Style JSON Editor の使い方

```bash
python StyleJsonEditor.py
```

* **開く**：`style.json` を読み込み（dict/list どちらでも OK）
* 表で行を選択 → 右ペインで `name / positive / negative` を編集
* **参照…** でフォルダ選択、**枚数更新** で画像枚数を表示
* **選択行を検証 / 全行を検証** で存在チェック・画像有無・name 重複を確認
* **保存オプション**：dict/list 切替、相対/絶対パス切替、相対の基準フォルダ設定

---

## アルゴリズム概要

* **パレット抽出**：KMeans（自動 k は Elbow 法 / `kneed`）
* **色空間**：OpenCV HSV（Hue: 0–179）
* **調和スコア**：

  * Complementary：色相差 ~180°
  * Analogous：近接（~±30°）
  * Monochromatic：色相差小＋S/V の整合
  * SplitComplementary／Triadic：3色関係
* **重み学習（任意）**：

  * 正/負のメトリクスをまとめてロジスティック回帰 → 係数を 0 以上にクリップ → 正規化
* **学習器**：RandomForest（既定）／LightGBM（任意）
* **特徴量**：調和 5 指標 + WeightedOverall + HSV 統計（Dom/Mean）

---

## ベストプラクティス / データ準備

* 正例・負例の**枚数バランス**を大きく偏らせない
* 解像度は問わないが、極小画像は避ける（既定で 600×400 に縮小して解析）
* 学習前に **「重み自動学習」** を ON にするとスタイル間の違いが強調されやすい
* LightGBM を使う場合、サンプル数が少ないと
  `Stopped training because there are no more leaves that meet the split requirements`
  の警告が出やすいので、**RandomForest** を推奨

---

## 既知の制限

* 画像の極端な色補正やフィルタに弱い場合があります
* Hue は OpenCV 基準（0–179）。他ライブラリの 0–360°表現と異なる点に注意
* マルチスレッドは学習/評価で使用（GUI は Qt スレッドセーフな範囲で更新）

---

## トラブルシューティング

* **LightGBM 警告**（葉の分割要件）
  → データ増強 or ハイパラ調整、難しければ RandomForest に切替。
* **プレビューが重い**
  → 画像リサイズ設定（抽出/調和タブの W/H）を小さめにする。
* **画像が読み込めない**
  → パスと拡張子、権限を確認。`style.json` の相対/絶対の整合もチェック。

---

## ライセンス

MIT License。研究・教育・社内 PoC 利用を想定。

---

## 謝辞 / クレジット

* OpenCV, scikit-learn, LightGBM, Matplotlib, PyQt6, NumPy, pandas, kneed
* UI/レポート仕様に関するフィードバックに感謝します。

---

## 変更履歴（抜粋）

* 0.2.0

  * 詳細タブを **QSplitter** 化（テキスト/プレビュー/グラフの高さをドラッグ調整）
  * グラフサイズを 75% に縮小（4.5×2.25）
  * 抽出パレット可視化、提案サマリー生成を追加
* 0.1.0

  * 初版（学習/評価、レポート、ギャップ図、プレビュー）

---

## 開発メモ

* 追加要望（例）

  * サムネイル一覧、ドラッグ＆ドロップで評価対象追加
  * 予測重要度の可視化（SHAP/Permutation Importance）
  * 3D カラースペース可視化（HSV / Lab）
  * 画像の自動トリミング（壁・床・家具領域の簡易セグメンテーション）

---

### クイックスタート（最短手順）

```bash
git clone <this-repo>
cd <this-repo>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python StyleJsonEditor.py        # style.json を用意
python ColorHarmonyAssistant.py  # 学習→評価
```
