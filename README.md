# フリマ出品アシスタント

商品写真をアップロードすると、Claude(AI)がタイトル・説明文・タグを自動生成します。
価格は含まれません(相場は出品者側で調べてください)。

## セットアップ

```bash
cd "フリマアプリ"
pip3 install -r requirements.txt
```

Anthropic APIキーを環境変数にセットしてください。

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 起動

```bash
python3 app.py
```

ブラウザで http://localhost:5001 を開いてください。

同じWi-Fiにいる人(お兄さんなど)に試してもらう場合は、このPCのIPアドレスを調べて
`http://<このPCのIPアドレス>:5001` にアクセスしてもらってください。
(例: Macなら `ipconfig getifaddr en0` でIPアドレス確認)

## 注意

- アップロードした画像は `uploads/` フォルダに保存されます。
- 生成された内容は必ず自分で確認・修正してから出品してください(ブランド名やサイズなどAIが誤認する場合があります)。
