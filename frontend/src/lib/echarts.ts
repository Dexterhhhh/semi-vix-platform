import { use } from 'echarts/core'
import { LineChart, ScatterChart, CandlestickChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent, AriaComponent } from 'echarts/components'
import { LabelLayout } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, ScatterChart, CandlestickChart, GridComponent, TooltipComponent,
  DataZoomComponent, AriaComponent, LabelLayout, CanvasRenderer])

export * from 'echarts/core'
