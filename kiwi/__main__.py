if __name__ == "__main__":
    from gevent import monkey

    print("monkey::patch_all")
    monkey.patch_all()
    
from base.style import is_debug

if __name__ == "__main__":
    import kiwi.app

    if is_debug():
        kiwi.app.test()
    kiwi.app.main()
