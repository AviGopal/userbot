from setuptools import setup, find_packages

setup(
    name="github-stalkerbot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "beautifulsoup4",
        'browser-cookie3',
        "click",
        "tqdm"
    ],
    entry_points={
        "console_scripts": ["stalkerbot=stalkerbot.cli:start"]
    }
)