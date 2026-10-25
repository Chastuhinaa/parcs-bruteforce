all: run

clean:
	rm -rf build out/BruteForce.jar out/HashCrack.jar

build: out/parcs.jar src/BruteForce.java src/HashCrack.java
	@rm -rf build && mkdir -p build
	@javac -encoding UTF-8 -cp out/parcs.jar -d build src/*.java
	@jar cf out/HashCrack.jar  -C build .
	@jar cf out/BruteForce.jar -C build .

run: build
	@cd out && java -cp 'parcs.jar:BruteForce.jar' BruteForce
