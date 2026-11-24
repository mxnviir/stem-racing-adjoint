# Evolution + adjoint: what the literature says, and what it means here (2026-11-24)

## The ideas that fit this problem
1. **Guided evolution strategies** (Maheswaranathan, Metz, Tucker, Choi, Sohl-Dickstein, ICML 2019, arXiv 1806.10230).
   Evolution samples random perturbations; the search distribution is stretched along a "guiding subspace" built from
   surrogate gradients that are correlated with the true gradient but biased in an unknown way. The estimator is a
   descent direction in expectation whatever the bias ("safe" bias), and it beat both plain ES and following the
   surrogate gradient directly. This is exactly our situation: coarse DAFoam (exact for the coarse model, biased for
   the good mesh) and ESI (weakly correlated) are surrogate gradients; the good-mesh CFD is the true objective.
2. **Self-guided ES** (Liu, Li, Qian, IJCAI 2020): build the guiding subspace from the history of estimated gradients
   (momentum, like SGD/Adam) and adapt the weight between the full space and the subspace. Used here: the last
   accepted step is a guide; guides are weighted by what they measurably did.
3. **Injecting external solutions into CMA-ES** (Hansen 2011, INRIA RR-7748, arXiv 1110.4181): gradient or Newton steps
   can be injected as candidates into an evolution's population, provided their step length is renormalised; one
   bad injected candidate costs about one population member. This is the "mixed pool" with a theory behind it.
4. **Memetic / Lamarckian hybrids** in aerodynamic shape design (global evolution + adjoint local search; e.g. the
   metamodel-assisted memetic algorithm of Kampolis/Asouti/Giannakoglou, Eng. Optim. 2012): the evolution explores
   globally, adjoint-driven local search refines, refined designs are written back (Lamarckian). Most of these use
   metamodels (predictors), which the owner's rules exclude; the structure, not the metamodel, is what we take.
5. **Multimodality** (Bons, He, Mader, Martins, AIAA J 2019; Chernukhin and Zingg): gradient-based multistart is
   efficient when the design space has few optima; a hybrid (evolution + gradient) is preferred as multimodality
   grows. Our coarse/medium probes found a valley (a half-grown pod is worse than none): the space is multimodal at
   the concept scale, smooth at the 0.1 mm scale.
6. **Sobolev / Helmholtz smoothing of node-based gradients** (Dick, Gauger, Schmidt; Najian Asl and Bletzinger 2023):
   free-form (per-node) shape gradients need smoothing to be usable steps; smoothing acts like a preconditioner.
   Our 4.5 mm Gaussian smoothing of every direction (random and adjoint alike) is this, and keeps the method free of
   shape parameters.
7. **Multi-fidelity with first-order consistency** (Alexandrov et al. 2001, trust-region model management; March and
   Willcox): a cheap model's gradient can drive a high-fidelity optimisation if it is corrected and steps are kept in
   a trust region checked by the expensive model. Here: coarse DAFoam proposes, the good mesh decides, step size
   chosen by CFD.
8. **Why continuous adjoints can mislead** (Lozano 2012; stellarator review arXiv 2005.07633; FV adjoint analysis
   arXiv 2009.07096): continuous-adjoint sensitivities need not be descent directions of the discretised problem,
   especially with upwind schemes and sharp geometry. Consistent with ESI's failures here; a discrete adjoint is
   consistent by construction.

## What it means for this project
- The adjoints should **propose**, evolution should **sample**, and CFD on the good mesh should **decide**, with each
  adjoint's weight set by how much drag its own probe actually removed (measured each round, not assumed).
- Small populations in high dimension: plain CMA-ES learns a covariance it cannot afford (the evolution branch's
  72-dimensional CMA, 96 SimScale cars, never beat the team pod). A guided subspace gives the population a direction
  from round one.
- Noise: the good-mesh morphed solves have a whole-signal SE of ~0.12 mN, while a 0.125 mm smooth move changes drag by
  0.4-1.0 mN, so single evaluations rank reliably; a fresh mesh per candidate (the evolution branch's SimScale route)
  adds mesh-to-mesh scatter of several mN and drowns small steps.

Sources: [Guided ES](https://arxiv.org/abs/1806.10230), [Self-guided ES](https://www.ijcai.org/proceedings/2020/205),
[Injecting solutions into CMA-ES](https://arxiv.org/abs/1110.4181),
[Asynchronous metamodel-assisted memetic algorithm](https://www.tandfonline.com/doi/full/10.1080/0305215X.2011.570758),
[Bons et al. 2019](https://mdolab.engin.umich.edu/bibliography/Bons2019a),
[Sobolev/implicit filtering, Najian Asl and Bletzinger](https://arxiv.org/abs/2109.15279),
[Multifidelity optimisation, March and Willcox](https://kiwi.oden.utexas.edu/papers/Multifidelity-optimization-March-Wang-Willcox.pdf),
[FV discrete adjoint analysis](https://arxiv.org/abs/2009.07096), [Adjoint methods review](https://arxiv.org/pdf/2005.07633).
