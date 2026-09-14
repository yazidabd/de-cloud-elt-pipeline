import json
import os
import tempfile

import load_to_snowflake


# cek unwrap_to_jsonl memecah wrapper jadi satu baris JSON per record
# dan tiap baris punya extraction_date serta source_file yang benar
def test_unwrap_to_jsonl_creates_one_line_per_record():
    wrapper = {
        "extraction_date": "2026-01-01",
        "source": "fakestoreapi",
        "record_count": 2,
        "data": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}],
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        landing_path = os.path.join(tmp_dir, "products_2026-01-01.json")
        with open(landing_path, "w") as f:
            json.dump(wrapper, f)

        output_dir = os.path.join(tmp_dir, "staging_tmp")
        result_path = load_to_snowflake.unwrap_to_jsonl(landing_path, output_dir)

        assert os.path.exists(result_path)
        with open(result_path) as f:
            lines = [json.loads(line) for line in f]

        assert len(lines) == 2
        assert lines[0]["extraction_date"] == "2026-01-01"
        assert lines[0]["source_file"] == "products_2026-01-01.json"
        assert lines[0]["record"] == {"id": 1, "title": "A"}
        assert lines[1]["record"] == {"id": 2, "title": "B"}
