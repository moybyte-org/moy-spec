# libmoy itself requires nothing. The IDF components below are what THIS example
# needs to do the host's four jobs -- a clock, buttons, persistence -- and they
# belong to the port, not to the library.
idf_component_register(
    SRCS "main.c"
    REQUIRES libmoy esp_timer esp_driver_gpio nvs_flash)
