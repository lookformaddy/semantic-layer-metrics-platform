.PHONY: test demo serve metrics clean

test:
	PYTHONPATH=src python -m pytest -q

demo:
	python examples/run_demo.py

serve:
	semantic-layer serve --port 8000

metrics:
	semantic-layer metrics

clean:
	rm -rf .pytest_cache
