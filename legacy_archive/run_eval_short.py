from multiprocessing import freeze_support

# run short evaluation to validate metrics pipeline
if __name__ == '__main__':
    freeze_support()
    from assault_sim.evaluation import evaluate_model as ev

    ev.EPISODES = 10
    ev.NUM_WORKERS = min(2, ev.NUM_WORKERS)

    ev.main()
