# 레이아웃 스트레스 검증

이 문서는 한 페이지에 담기지 않는 요소가 페이지 경계에서 어떻게 처리되는지만 확인한다. 표 헤더 반복, 디스플레이 수식 분할, 페이지보다 긴 코드 블록 세 가지를 다룬다.

## 1. 여러 페이지에 걸치는 표

아래 표는 45행이라 반드시 페이지를 넘어간다. 헤더 행이 다음 페이지에서도 반복되어야 하고, 행이 셀 중간에서 쪼개지지 않아야 한다.

| 실험 번호 | 모델 이름 | 성공률 | 지연시간 | 파라미터 |
| --- | --- | --- | --- | --- |
| 실험 01 | 모델-01 | 57.1% | 33ms | 17M |
| 실험 02 | 모델-02 | 64.2% | 36ms | 34M |
| 실험 03 | 모델-03 | 71.3% | 39ms | 51M |
| 실험 04 | 모델-04 | 78.4% | 42ms | 68M |
| 실험 05 | 모델-05 | 85.5% | 45ms | 85M |
| 실험 06 | 모델-06 | 92.6% | 48ms | 102M |
| 실험 07 | 모델-07 | 54.7% | 51ms | 119M |
| 실험 08 | 모델-08 | 61.8% | 54ms | 136M |
| 실험 09 | 모델-09 | 68.9% | 57ms | 153M |
| 실험 10 | 모델-10 | 75.0% | 60ms | 170M |
| 실험 11 | 모델-11 | 82.1% | 63ms | 187M |
| 실험 12 | 모델-12 | 89.2% | 66ms | 204M |
| 실험 13 | 모델-13 | 51.3% | 69ms | 221M |
| 실험 14 | 모델-14 | 58.4% | 72ms | 238M |
| 실험 15 | 모델-15 | 65.5% | 75ms | 255M |
| 실험 16 | 모델-16 | 72.6% | 78ms | 272M |
| 실험 17 | 모델-17 | 79.7% | 81ms | 289M |
| 실험 18 | 모델-18 | 86.8% | 84ms | 306M |
| 실험 19 | 모델-19 | 93.9% | 87ms | 323M |
| 실험 20 | 모델-20 | 55.0% | 90ms | 340M |
| 실험 21 | 모델-21 | 62.1% | 33ms | 357M |
| 실험 22 | 모델-22 | 69.2% | 36ms | 374M |
| 실험 23 | 모델-23 | 76.3% | 39ms | 391M |
| 실험 24 | 모델-24 | 83.4% | 42ms | 408M |
| 실험 25 | 모델-25 | 90.5% | 45ms | 425M |
| 실험 26 | 모델-26 | 52.6% | 48ms | 442M |
| 실험 27 | 모델-27 | 59.7% | 51ms | 459M |
| 실험 28 | 모델-28 | 66.8% | 54ms | 476M |
| 실험 29 | 모델-29 | 73.9% | 57ms | 493M |
| 실험 30 | 모델-30 | 81.0% | 60ms | 510M |
| 실험 31 | 모델-31 | 88.1% | 63ms | 527M |
| 실험 32 | 모델-32 | 95.2% | 66ms | 544M |
| 실험 33 | 모델-33 | 57.3% | 69ms | 561M |
| 실험 34 | 모델-34 | 64.4% | 72ms | 578M |
| 실험 35 | 모델-35 | 71.5% | 75ms | 595M |
| 실험 36 | 모델-36 | 78.6% | 78ms | 612M |
| 실험 37 | 모델-37 | 85.7% | 81ms | 629M |
| 실험 38 | 모델-38 | 92.8% | 84ms | 646M |
| 실험 39 | 모델-39 | 54.9% | 87ms | 663M |
| 실험 40 | 모델-40 | 62.0% | 90ms | 680M |
| 실험 41 | 모델-41 | 69.1% | 33ms | 697M |
| 실험 42 | 모델-42 | 76.2% | 36ms | 714M |
| 실험 43 | 모델-43 | 83.3% | 39ms | 731M |
| 실험 44 | 모델-44 | 90.4% | 42ms | 748M |
| 실험 45 | 모델-45 | 97.5% | 45ms | 765M |

표가 끝난 뒤의 문단이다. 표 바로 다음 문단은 예외적으로 들여쓰지 않는다.

## 2. 페이지 경계 근처의 디스플레이 수식

아래 문단들은 디스플레이 수식이 페이지 경계에 걸리도록 길이를 맞춘 것이다. 수식이 두 조각으로 쪼개져 분수선과 적분 기호가 위아래로 잘리면 안 된다. 이 문단은 그 상황을 만들기 위해 충분히 길게 작성되었으며, 실제 논문에서 자주 나타나는 문단 밀도를 재현한다. 한글은 어절 단위로만 줄이 나뉘어야 하고, 영어 전문용어가 섞여도 마찬가지다.

두 번째 문단이다. 페이지 경계의 위치를 조절하려고 존재하며 내용 자체에는 의미가 없다. 다만 실제 번역문과 비슷한 길이와 밀도를 유지하여 조판 결과가 현실적인 조건에서 측정되도록 한다. 수식 앞 문단이 길수록 수식이 페이지 하단에 걸릴 확률이 높아진다.

$$\mathcal{L}_{\text{total}}(\theta) = \sum_{i=1}^{N} \frac{\exp\left(-\frac{\|a_i - \pi_\theta(o_i)\|^2}{2\sigma^2}\right)}{\sum_{j=1}^{K} \exp\left(-\frac{\|a_j - \pi_\theta(o_j)\|^2}{2\sigma^2}\right)} + \lambda \int_0^\infty e^{-x^2} \, dx$$

수식 다음 문단이다. 수식이 온전히 한 페이지에 들어갔는지를 이 문단의 위치로 가늠할 수 있다.

## 3. 한 페이지보다 긴 코드 블록

아래 코드 블록은 60줄이 넘어 한 페이지에 들어가지 않는다. `break-inside: avoid`가 이런 경우 무시되고 정상적으로 쪼개져야 하며, 잘려서 사라지면 안 된다.

```python
def forward(self, hidden_state, attention_mask):
    layer_01 = self.block_01(hidden_state, attention_mask)  # 블록 1 통과
    layer_02 = self.block_02(layer_01, attention_mask)  # 블록 2 통과
    layer_03 = self.block_03(layer_02, attention_mask)  # 블록 3 통과
    layer_04 = self.block_04(layer_03, attention_mask)  # 블록 4 통과
    layer_05 = self.block_05(layer_04, attention_mask)  # 블록 5 통과
    layer_06 = self.block_06(layer_05, attention_mask)  # 블록 6 통과
    layer_07 = self.block_07(layer_06, attention_mask)  # 블록 7 통과
    layer_08 = self.block_08(layer_07, attention_mask)  # 블록 8 통과
    layer_09 = self.block_09(layer_08, attention_mask)  # 블록 9 통과
    layer_10 = self.block_10(layer_09, attention_mask)  # 블록 10 통과
    layer_11 = self.block_11(layer_10, attention_mask)  # 블록 11 통과
    layer_12 = self.block_12(layer_11, attention_mask)  # 블록 12 통과
    layer_13 = self.block_13(layer_12, attention_mask)  # 블록 13 통과
    layer_14 = self.block_14(layer_13, attention_mask)  # 블록 14 통과
    layer_15 = self.block_15(layer_14, attention_mask)  # 블록 15 통과
    layer_16 = self.block_16(layer_15, attention_mask)  # 블록 16 통과
    layer_17 = self.block_17(layer_16, attention_mask)  # 블록 17 통과
    layer_18 = self.block_18(layer_17, attention_mask)  # 블록 18 통과
    layer_19 = self.block_19(layer_18, attention_mask)  # 블록 19 통과
    layer_20 = self.block_20(layer_19, attention_mask)  # 블록 20 통과
    layer_21 = self.block_21(layer_20, attention_mask)  # 블록 21 통과
    layer_22 = self.block_22(layer_21, attention_mask)  # 블록 22 통과
    layer_23 = self.block_23(layer_22, attention_mask)  # 블록 23 통과
    layer_24 = self.block_24(layer_23, attention_mask)  # 블록 24 통과
    layer_25 = self.block_25(layer_24, attention_mask)  # 블록 25 통과
    layer_26 = self.block_26(layer_25, attention_mask)  # 블록 26 통과
    layer_27 = self.block_27(layer_26, attention_mask)  # 블록 27 통과
    layer_28 = self.block_28(layer_27, attention_mask)  # 블록 28 통과
    layer_29 = self.block_29(layer_28, attention_mask)  # 블록 29 통과
    layer_30 = self.block_30(layer_29, attention_mask)  # 블록 30 통과
    layer_31 = self.block_31(layer_30, attention_mask)  # 블록 31 통과
    layer_32 = self.block_32(layer_31, attention_mask)  # 블록 32 통과
    layer_33 = self.block_33(layer_32, attention_mask)  # 블록 33 통과
    layer_34 = self.block_34(layer_33, attention_mask)  # 블록 34 통과
    layer_35 = self.block_35(layer_34, attention_mask)  # 블록 35 통과
    layer_36 = self.block_36(layer_35, attention_mask)  # 블록 36 통과
    layer_37 = self.block_37(layer_36, attention_mask)  # 블록 37 통과
    layer_38 = self.block_38(layer_37, attention_mask)  # 블록 38 통과
    layer_39 = self.block_39(layer_38, attention_mask)  # 블록 39 통과
    layer_40 = self.block_40(layer_39, attention_mask)  # 블록 40 통과
    layer_41 = self.block_41(layer_40, attention_mask)  # 블록 41 통과
    layer_42 = self.block_42(layer_41, attention_mask)  # 블록 42 통과
    layer_43 = self.block_43(layer_42, attention_mask)  # 블록 43 통과
    layer_44 = self.block_44(layer_43, attention_mask)  # 블록 44 통과
    layer_45 = self.block_45(layer_44, attention_mask)  # 블록 45 통과
    layer_46 = self.block_46(layer_45, attention_mask)  # 블록 46 통과
    layer_47 = self.block_47(layer_46, attention_mask)  # 블록 47 통과
    layer_48 = self.block_48(layer_47, attention_mask)  # 블록 48 통과
    layer_49 = self.block_49(layer_48, attention_mask)  # 블록 49 통과
    layer_50 = self.block_50(layer_49, attention_mask)  # 블록 50 통과
    layer_51 = self.block_51(layer_50, attention_mask)  # 블록 51 통과
    layer_52 = self.block_52(layer_51, attention_mask)  # 블록 52 통과
    layer_53 = self.block_53(layer_52, attention_mask)  # 블록 53 통과
    layer_54 = self.block_54(layer_53, attention_mask)  # 블록 54 통과
    layer_55 = self.block_55(layer_54, attention_mask)  # 블록 55 통과
    layer_56 = self.block_56(layer_55, attention_mask)  # 블록 56 통과
    layer_57 = self.block_57(layer_56, attention_mask)  # 블록 57 통과
    layer_58 = self.block_58(layer_57, attention_mask)  # 블록 58 통과
    layer_59 = self.block_59(layer_58, attention_mask)  # 블록 59 통과
    layer_60 = self.block_60(layer_59, attention_mask)  # 블록 60 통과
    return layer_60
```

마지막 문단이다. 코드 블록이 페이지를 넘어가면서도 모든 줄이 살아남았는지 확인한다.
