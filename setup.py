import setuptools

setuptools.setup(
    name="dan-test",
    version="0.0.1",
    author="HPE",
    author_email="daniel.illescas@hpe.com",
    description="A kafka consumer package",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
