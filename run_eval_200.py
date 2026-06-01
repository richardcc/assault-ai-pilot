from multiprocessing import freeze_support

# run short evaluation to validate impact of OptionExecutor change
if __name__ == '__main__':
    freeze_support()
    from assault_sim.evaluation import evaluate_model as ev

    ev.EPISODES = 200
    ev.NUM_WORKERS = min(4, ev.NUM_WORKERS)

    ev.main()
