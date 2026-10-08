package main

// A file of go functions for the tinygo demo: load imports every export.

//export add
func add(a, b uint32) uint32 { return a + b }

//export square
func square(n uint32) uint32 { return n * n }

func main() {}
