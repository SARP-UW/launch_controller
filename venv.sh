if [ -e .venv/bin/activate ]; then
	source .venv/bin/activate
else
    echo "[ Creating virtual environment ]"
	echo ""
	echo "NOTE: Restart the terminal session and run this script again or the dependencies will not be recognized by python."
	echo ""
	python3 -m venv .venv
	source .venv/bin/activate
fi
echo "[ Initializing virtual environment ]"
echo ""

echo "[ Installing requirements ]"
echo ""
pip3 install -r requirements.txt