# Training EasyOCR for Hungarian License Plate Fonts

This guide explains how to fine-tune EasyOCR to better recognize Hungarian license plate fonts.

---

## 1. Get the Right Font

Use **HuLi** by Andris Csanyi – the official 2022 Hungarian license plate font:

- **[HuLi on DaFont](https://www.dafont.com/huli.font)** – Download `HuLi-Regular.ttf` (free, donationware)

Save it somewhere like `fonts/HuLi-Regular.ttf`.

*Old Hungarian plates used FE-Schrift; since July 2022 the new format uses HuLi. For current plates, HuLi is the correct choice.*

---

## 2. Generate Synthetic Training Data

Use **TextRecognitionDataGenerator** (TRDG):

```bash
git clone https://github.com/Belval/TextRecognitionDataGenerator.git
cd TextRecognitionDataGenerator
pip install trdg Pillow==9.5.0
```

Create `generate_plate_data.py`:

```python
from trdg.generators import GeneratorFromStrings
from tqdm import tqdm
import os
import random
import string

# Hungarian plate format: ABC-123 (3 letters, hyphen, 3 digits) or newer formats
def gen_plate():
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    nums = ''.join(random.choices(string.digits, k=3))
    return f"{letters}-{nums}"

# Add variations: ABC 123, ABC123, EU ABC-123, etc.
plates = [gen_plate() for _ in range(5000)]
plates += [f"EU {gen_plate()}" for _ in range(1000)]  # EU format

# Generate with HuLi (2022 Hungarian plate font)
os.makedirs("plate_output", exist_ok=True)
generator = GeneratorFromStrings(
    plates,
    fonts=["path/to/HuLi-Regular.ttf"],
    skewing_angle=5,
    random_skew=True,
    blur=1,
    random_blur=True,
    background_type=0,
)

with open("plate_output/labels.txt", "w") as f:
    for i, (img, label) in enumerate(tqdm(generator, total=len(plates))):
        img.save(f"plate_output/img_{i:05d}.png")
        f.write(f"img_{i:05d}.png\t{label}\n")
```

Run:

```bash
python generate_plate_data.py
```

---

## 3. Train the Recognition Model

Clone **deep-text-recognition-benchmark**:

```bash
git clone https://github.com/clovaai/deep-text-recognition-benchmark
cd deep-text-recognition-benchmark
pip install fire lmdb opencv-python natsort nltk torch torchvision
```

Convert your dataset to LMDB format:

```bash
python create_lmdb_dataset.py plate_output plate_output/labels.txt plate_lmdb
```

**Note:** You may need to edit `create_lmdb_dataset.py` if your labels format differs (e.g. tab vs space separator). The script expects `imagepath\tlabel` per line.

Download the pre-trained model: [TPS-ResNet-BiLSTM-Attn.pth](https://drive.google.com/drive/folders/15WPsuPJDCzhp2SvYZLRj8mAlT3zmoAMW) (linked from the deep-text-recognition-benchmark repo). Place it in the `deep-text-recognition-benchmark` folder.

Fine-tune:

```bash
python train.py --train_data plate_lmdb --valid_data plate_lmdb --select_data "/" \
  --batch_ratio 1.0 --Transformation TPS --FeatureExtraction ResNet --SequenceModeling BiLSTM \
  --Prediction Attn --batch_size 32 --data_filtering_off --workers 0 \
  --batch_max_length 12 --num_iter 5000 --valInterval 500 \
  --saved_model TPS-ResNet-BiLSTM-Attn.pth --FT
```

**Parameters to adjust:**
- `batch_max_length`: Set to your longest plate string length (e.g. "EU ABC-123" = 12 chars)
- `num_iter`: More = longer training (5000–20000 typical)

---

## 4. Integrate Custom Model into Your App

After training, you need **three files** with the same base name:

1. `hungarian_plate.pth` – trained model weights
2. `hungarian_plate.yaml` – config (character set, etc.)
3. `hungarian_plate.py` – network architecture definition

Use the [custom_example.zip](https://jaided.ai/easyocr/modelhub/) from EasyOCR’s modelhub as a template. The architecture must match what you trained (TPS-ResNet-BiLSTM-Attn).

Place them:

- `~/.EasyOCR/user_network/`: `hungarian_plate.py`, `hungarian_plate.yaml`
- `~/.EasyOCR/model/`: `hungarian_plate.pth`

Then in `plate_ocr.py`, load with:

```python
_ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False, recog_network="hungarian_plate")
```

---

## 5. Data Format Notes

- **Labels file format:** `imagepath\tlabel` per line (tab-separated). TRDG outputs `img_00001.png\tABC-123`.
- **LMDB conversion:** If `create_lmdb_dataset.py` expects a different format, edit the parsing (see the FreeCodeCamp tutorial for common fixes).
- **Character set:** Ensure your `yaml` config lists all chars: `ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-`

---

## 6. Quick Tips

| Tip | Notes |
|-----|-------|
| **Add augmentation** | Use TRDG’s `blur`, `random_skew`, `distorsion` to mimic real camera noise |
| **Mix in real data** | If you have real plate crops from debug, add them with manual labels |
| **Format rules** | Hungarian plates: 3 letters + 3 digits; EU format adds "EU" prefix; use `allowlist` in `readtext()` to constrain output |
| **Character set** | Hungarian plates use A–Z and 0–9; include hyphen for separator. Update the yaml to match |
| **EasyOCR trainer** | EasyOCR also has its own [trainer](https://github.com/JaidedAI/EasyOCR/tree/master/trainer) – an alternative to deep-text-recognition-benchmark |

---

## 7. Alternative: No Custom Training

Before investing in training, try:

1. **Preprocessing** – your existing CLAHE + upscaling helps
2. **allowlist** – restrict to `ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-`
3. **Tuning** – `text_threshold`, `contrast_ths`, `adjust_contrast` in `readtext()`

If that’s still not enough, custom training on synthetic HuLi data usually gives a significant boost for Hungarian plates.
