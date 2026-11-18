# dsh-manager 3.3.3

试听文本按音色语言走，不再让英文音色念中文。

## 改动

音色前缀 → 语言 → 试听句子：

| 前缀 | 语言 | 试听文本 |
| --- | --- | --- |
| `zf_` `zm_` | 中文 | 你好，这是这个音色的试听。 |
| `af_` `am_` `bf_` `bm_` | 英文 | Hello, this is a preview of this voice. |
| `jf_` `jm_` | 日文 | こんにちは、この音色の試聴です。 |
| `hf_` `hm_` | 印地语 | नमस्ते, यह इस आवाज़ का पूर्वावलोकन है। |
| `ef_` `em_` | 西班牙语 | Hola, esta es una prueba de esta voz. |
| `ff_` | 法语 | Bonjour, voici un aperçu de cette voix. |
| `if_` `im_` | 意大利语 | Ciao, questa è un'anteprima di questa voce. |
| `pf_` `pm_` | 葡萄牙语 | Olá, esta é uma prévia desta voz. |
| 自建音色/未知 | 英文 | Hello, this is a preview of this voice. |

两平台同一套映射（Windows `AudioCppService.PreviewText`、Linux `preview_text`）。
