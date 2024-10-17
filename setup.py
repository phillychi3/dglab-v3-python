import setuptools

with open("readmd.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="dglabv3",
    version="0.1",
    author='phillychi3',
    author_email='phillychi3@gmail.com',
    description='a dglab v3 lib',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/phillychi3/dc_grafana",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",],
    packages = setuptools.find_packages(where="."),
    package_dir = {"":"."},
    python_requires=">=3.7",
    install_requires=["websocket-client","qrcode"]
)
