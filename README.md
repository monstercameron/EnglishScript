# English Script Programming Language Compiler

The English Script Programming Language Compiler is a python application that uses OpenAI's GPT-3.5 model to translate English scripts into JavaScript. The application follows certain rules and uses an alias system to understand and transcribe the English scripts. It creates an output JavaScript file and also has the capability to execute this file.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python (>= 3.7)
- [openai](https://github.com/openai/openai) Python package
- [python-dotenv](https://pypi.org/project/python-dotenv/)
- An OpenAI API key

### Installing

1. Clone this repository.
```bash
git clone https://github.com/your-username/english-script-compiler
```

2. Navigate into the project directory.
```bash
cd english-script-compiler
```

3. Install the necessary packages.
```bash
pip install -r requirements.txt
```

### Usage

To use this application, follow the below steps:

1. Create a `.env` file in the root of your project directory and add your OpenAI API key:
```bash
OPENAI_API_KEY=your_api_key
```

2. Now, you can run the main python script, `main.py`:
```bash
python main.py
```

This script will read an English script and use the OpenAI GPT-3.5 model to translate it into a JavaScript file located at `output/index.js`.

### Code Overview

The application's workflow is as follows:

1. Import necessary libraries and load environment variables.
2. Retrieve and set OpenAI API key.
3. Import and set the translation rules and aliases.
4. Use OpenAI's API to perform a chat completion and function call, requesting a JavaScript translation of an English script.
5. Extract the JavaScript translation from the API response and save it into a `.js` file.
6. Execute the resulting JavaScript file.

### Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

### License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.