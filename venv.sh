if [ -e .venv/bin/activate ]; then
	source .venv/bin/activate
else
    echo "[ Creating virtual environment ]"
	echo ""
	python3 -m venv .venv
	source .venv/bin/activate
fi
echo "[ Initializing virtual environment ]"
echo ""

echo "[ Installing requirements ]"
echo ""
pip3 install -r requirements.txt