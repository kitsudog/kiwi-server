from base.style import is_debug

if __name__ == "__main__":
    import kiwi.app

    if is_debug():
        kiwi.app.test()
    kiwi.app.main()
