import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cmt_solutions",
    version="1.0.0",
    author="Quakecore",
    description="Package for obtaining and processing CMT solutions",
    url="https://github.com/ucgmsim/cmt_solutions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    package_data={"cmt_solutions": ["data/*"]},
)
